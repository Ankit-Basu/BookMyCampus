from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.bookings.exceptions import BookingError
from apps.notifications.models import Notification
from apps.notifications.services import notify_many

from .models import Consumable, Issuance


def _alert_if_low(c):
    if c.stock <= c.reorder_level:
        recipients = list(User.objects.filter(role__in=[Role.FACILITY_MANAGER]))
        if c.resource_id:
            recipients += list(c.resource.custodians.all())
        notify_many(
            recipients, Notification.Kind.STOCK, f"Low stock: {c.name}",
            f"{c.stock} {c.unit} left (reorder at {c.reorder_level}).", link="/admin/consumables", email=False,
        )


def issue(consumable_id, quantity, user, booking=None):
    if quantity < 1:
        raise BookingError("bad_quantity", "Quantity must be at least 1.")
    with transaction.atomic():
        # Atomic decrement guarded by the WHERE clause — no oversell under concurrency.
        n = Consumable.objects.filter(pk=consumable_id, stock__gte=quantity).update(stock=F("stock") - quantity)
        if not n:
            c = Consumable.objects.filter(pk=consumable_id).first()
            raise BookingError("out_of_stock", f"Only {c.stock if c else 0} left.", http_status=409)
        c = Consumable.objects.get(pk=consumable_id)
        iss = Issuance.objects.create(consumable=c, booking=booking, user=user, quantity=quantity)
    _alert_if_low(c)
    return iss


def issue_for_booking(booking, consumable_id, quantity, user):
    return issue(consumable_id, quantity, booking.user, booking)


def return_issuance(iss, quantity=None):
    if iss.status != Issuance.Status.ISSUED:
        raise BookingError("already_closed", "This issuance is already closed.")
    qty = iss.quantity if quantity is None else min(int(quantity), iss.quantity)
    with transaction.atomic():
        if iss.consumable.kind == Consumable.Kind.ACCESSORY or qty:
            Consumable.objects.filter(pk=iss.consumable_id).update(stock=F("stock") + qty)
        iss.returned_quantity = qty
        iss.returned_at = timezone.now()
        iss.status = Issuance.Status.RETURNED if qty else Issuance.Status.CONSUMED
        iss.save(update_fields=["returned_quantity", "returned_at", "status"])
    return iss
