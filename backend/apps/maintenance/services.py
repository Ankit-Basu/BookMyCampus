from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.bookings.exceptions import BookingError, is_exclusion_violation
from apps.bookings.models import BookingSlot
from apps.bookings.services import displace, tsrange
from apps.notifications.models import Notification
from apps.notifications.services import notify_many

from .models import MaintenanceWindow


def schedule(resource, start, end, *, title, kind=MaintenanceWindow.Kind.SCHEDULED, notes="", by=None):
    """
    Claim the resource for maintenance. Overlapping bookings are displaced (and told), then the
    window is written into the occupancy ledger. If a booking sneaks in between those two steps the
    slot insert fails on the exclusion constraint and we simply retry.
    """
    if end <= start:
        raise BookingError("invalid_period", "Maintenance must end after it starts.")
    for _attempt in range(3):
        try:
            with transaction.atomic():
                displaced = displace(resource, start, end, f"{resource.name} is under maintenance ({title})", Notification.Kind.MAINTENANCE)
                window = MaintenanceWindow.objects.create(
                    resource=resource, kind=kind, title=title, notes=notes, period=tsrange(start, end),
                    reported_by=by, displaced_bookings=displaced,
                    status=MaintenanceWindow.Status.IN_PROGRESS if start <= timezone.now() else MaintenanceWindow.Status.PLANNED,
                )
                BookingSlot.objects.create(
                    resource=resource, period=window.period, kind=BookingSlot.Kind.MAINTENANCE, maintenance=window, label=title
                )
                if kind == MaintenanceWindow.Kind.BREAKDOWN:
                    resource.status = resource.Status.DOWN
                    resource.save(update_fields=["status"])
        except IntegrityError as exc:
            if is_exclusion_violation(exc):
                continue
            raise
        notify_many(
            resource.custodians.all(), Notification.Kind.MAINTENANCE,
            f"{'Breakdown' if kind == 'breakdown' else 'Maintenance'}: {resource.name}",
            f"{title}. {timezone.localtime(start):%d %b %H:%M} → {timezone.localtime(end):%d %b %H:%M}. "
            f"{displaced} booking(s) displaced.",
            link="/admin/maintenance",
        )
        return window
    raise BookingError("busy", "Could not claim the window — overlapping maintenance already exists.", http_status=409)


def report_breakdown(resource, by, title, notes="", hours=24):
    now = timezone.now()
    return schedule(resource, now, now + timedelta(hours=hours), title=title, kind=MaintenanceWindow.Kind.BREAKDOWN, notes=notes, by=by)


def resolve(window, now=None):
    """Close a window early and give the rest of the time back to the booking pool."""
    now = now or timezone.now()
    with transaction.atomic():
        start = window.period.lower
        end = max(min(now, window.period.upper), start + timedelta(minutes=1))
        window.period = tsrange(start, end)
        window.status = MaintenanceWindow.Status.DONE
        window.resolved_at = now
        window.save(update_fields=["period", "status", "resolved_at"])
        BookingSlot.objects.filter(maintenance=window).update(period=window.period)
        BookingSlot.objects.filter(maintenance=window, period__endswith__lte=now).delete()
        r = window.resource
        if r.status == r.Status.DOWN:
            r.status = r.Status.ACTIVE
            r.save(update_fields=["status"])
    return window


def cancel(window):
    with transaction.atomic():
        window.status = MaintenanceWindow.Status.CANCELLED
        window.save(update_fields=["status"])
        BookingSlot.objects.filter(maintenance=window).delete()
        r = window.resource
        if window.kind == MaintenanceWindow.Kind.BREAKDOWN and r.status == r.Status.DOWN:
            r.status = r.Status.ACTIVE
            r.save(update_fields=["status"])
    return window
