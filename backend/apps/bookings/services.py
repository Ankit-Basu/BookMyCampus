"""
Booking engine.

The guarantee "no two live occupancies of a resource overlap" is enforced by PostgreSQL through
two EXCLUDE USING gist constraints (see models.py and docs/CONFLICT_PREVENTION.md). This module
never checks "is the slot free?" and then inserts — that check-then-act pattern is exactly the race
that causes double-booking. Instead it simply tries to insert and translates the database's refusal
(SQLSTATE 23P01) into a friendly 409.
"""
import random
import time
from datetime import timedelta

from dateutil.rrule import DAILY, WEEKLY, rrule
from django.conf import settings
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Q
from django.utils import timezone
from psycopg.types.range import Range

from apps.accounts.models import Role, User
from apps.notifications.models import Notification
from apps.notifications.services import notify
from apps.rules.models import Policy
from apps.rules.services import validate_request

from .exceptions import BookingError, RuleViolation, SlotConflict, is_deadlock, is_exclusion_violation
from .models import Booking, BookingAttempt, BookingSlot, CheckIn, NoShow, RecurrenceRule, SlotWatch

MAX_OCCURRENCES = 52
DEADLOCK_RETRIES = 25


def tsrange(start, end):
    return Range(start, end, bounds="[)")


def describe_conflict(resource, start, end):
    """After the DB refused an insert, find what is occupying the slot so we can explain it."""
    slot = (
        BookingSlot.objects.filter(resource=resource, period__overlap=(start, end))
        .select_related("booking", "timetable_entry")
        .first()
    )
    if not slot:
        return {}
    info = {"kind": slot.kind, "start": slot.period.lower.isoformat(), "end": slot.period.upper.isoformat()}
    if slot.kind == BookingSlot.Kind.TIMETABLE:
        info["label"] = slot.label
    elif slot.kind == BookingSlot.Kind.MAINTENANCE:
        info["label"] = "Maintenance"
    else:
        info["label"] = "Already booked"
    return info


def _log_attempt(user, resource, start, end, outcome, reason=""):
    try:
        BookingAttempt.objects.create(
            user=user, resource=resource, period=tsrange(start, end), outcome=outcome, reason=reason[:240]
        )
    except Exception:  # analytics must never break booking
        pass


def _insert(user, resource, start, end, *, title, purpose="", on_behalf_of="", attendees=1, recurrence=None, index=None):
    """
    Insert booking + ledger slot inside a savepoint. Raises SlotConflict if PostgreSQL refuses.
    Callers must already be inside transaction.atomic().
    """
    from apps.approvals.services import attach_class_signoff, attach_workflow, resolve_workflow

    workflow = resolve_workflow(resource, user)
    class_signoff = not workflow and user.role == Role.STUDENT and bool(on_behalf_of.strip())
    for attempt in range(DEADLOCK_RETRIES):
        try:
            booking = _claim(user, resource, start, end, workflow or class_signoff, title=title, purpose=purpose,
                             on_behalf_of=on_behalf_of, attendees=attendees, recurrence=recurrence, index=index)
            break
        except OperationalError as exc:
            # Two inserts that race on the same GiST key each wait for the other's verdict;
            # PostgreSQL breaks the tie by aborting one ("deadlock detected"). The savepoint is
            # rolled back, and the retry now sees the winner's committed row → clean 409.
            if not is_deadlock(exc) or attempt == DEADLOCK_RETRIES - 1:
                raise
            # exponential backoff with full jitter, so retrying requests stop colliding in lockstep
            time.sleep(random.uniform(0, min(0.4, 0.01 * 2**attempt)))
    if workflow:
        attach_workflow(booking, workflow)
    elif class_signoff:
        attach_class_signoff(booking)
    return booking


def _claim(user, resource, start, end, needs_approval, *, title, purpose, on_behalf_of, attendees, recurrence, index):
    try:
        with transaction.atomic():
            booking = Booking.objects.create(
                resource=resource,
                user=user,
                title=title,
                purpose=purpose,
                on_behalf_of=on_behalf_of,
                attendees=attendees,
                period=tsrange(start, end),
                status=Booking.Status.PENDING if needs_approval else Booking.Status.CONFIRMED,
                recurrence=recurrence,
                occurrence_index=index,
            )
            BookingSlot.objects.create(
                resource=resource, period=booking.period, kind=BookingSlot.Kind.BOOKING, booking=booking, label=title
            )
    except IntegrityError as exc:
        if is_exclusion_violation(exc):
            raise SlotConflict(details=describe_conflict(resource, start, end)) from None
        raise
    return booking


def _announce(booking):
    if booking.status == Booking.Status.CONFIRMED:
        notify(
            booking.user,
            Notification.Kind.CONFIRMED,
            f"Booked: {booking.resource.name}",
            f"{timezone.localtime(booking.start):%a %d %b, %H:%M}–{timezone.localtime(booking.end):%H:%M}. "
            f"Reference {booking.reference}. Check in within {Policy.get().grace_minutes} min of start.",
            booking=booking,
            link=f"/bookings/{booking.id}",
        )


def create_booking(user, resource, start, end, *, title, purpose="", on_behalf_of="", attendees=1):
    try:
        validate_request(user, resource, start, end, attendees, check_quota=False)
        with transaction.atomic():
            # Serialise quota checks per user (cheap row lock). Slot correctness does not need it.
            User.objects.select_for_update().only("id").get(pk=user.pk)
            from apps.rules.services import check_quotas

            check_quotas(user, resource, start, end)
            booking = _insert(
                user, resource, start, end, title=title, purpose=purpose, on_behalf_of=on_behalf_of, attendees=attendees
            )
    except SlotConflict as exc:
        _log_attempt(user, resource, start, end, BookingAttempt.Outcome.CONFLICT, exc.details.get("label", ""))
        raise
    except RuleViolation as exc:
        _log_attempt(user, resource, start, end, BookingAttempt.Outcome.RULE, exc.code)
        raise
    _log_attempt(user, resource, start, end, BookingAttempt.Outcome.BOOKED)
    _announce(booking)
    return booking


def expand_recurrence(start, end, *, freq, interval=1, weekdays=None, until=None, count=None):
    duration = end - start
    kwargs = {"dtstart": start, "interval": max(1, interval)}
    if weekdays and freq == RecurrenceRule.Freq.WEEKLY:
        kwargs["byweekday"] = sorted(set(weekdays))
    if until:
        local = timezone.localtime(start)
        kwargs["until"] = local.replace(year=until.year, month=until.month, day=until.day, hour=23, minute=59)
    kwargs["count"] = min(count or MAX_OCCURRENCES, MAX_OCCURRENCES) if not until else None
    local_start = timezone.localtime(start)
    kwargs["dtstart"] = local_start.replace(tzinfo=None)
    if "until" in kwargs:
        kwargs["until"] = kwargs["until"].replace(tzinfo=None)
    tz = timezone.get_current_timezone()
    occurrences = []
    for dt in rrule(DAILY if freq == RecurrenceRule.Freq.DAILY else WEEKLY, **kwargs):
        s = timezone.make_aware(dt, tz)  # keeps wall-clock time stable across DST
        occurrences.append((s, s + duration))
        if len(occurrences) >= MAX_OCCURRENCES:
            break
    return occurrences


def create_recurring(
    user, resource, start, end, *, title, purpose="", on_behalf_of="", attendees=1,
    freq="weekly", interval=1, weekdays=None, until=None, count=None, conflict_policy="skip",
):
    """
    Expand a series and claim each occurrence independently. Each occurrence runs in its own
    savepoint so a mid-series conflict (a lecture, someone else's booking, a blackout) only skips
    that date — or, with conflict_policy='abort', rolls the whole series back.
    """
    if not user.can_book_recurring:
        raise RuleViolation("recurring_not_permitted", "Recurring bookings are available to faculty and staff.", http_status=403)
    occurrences = expand_recurrence(start, end, freq=freq, interval=interval, weekdays=weekdays, until=until, count=count)
    if not occurrences:
        raise RuleViolation("empty_series", "That recurrence produces no dates.")

    created, skipped = [], []
    with transaction.atomic():
        rule = RecurrenceRule.objects.create(
            freq=freq, interval=interval, weekdays=weekdays or [], until=until, count=count,
            conflict_policy=conflict_policy, created_by=user, requested_occurrences=len(occurrences),
        )
        for i, (s, e) in enumerate(occurrences):
            try:
                validate_request(user, resource, s, e, attendees)
                b = _insert(
                    user, resource, s, e, title=title, purpose=purpose, on_behalf_of=on_behalf_of,
                    attendees=attendees, recurrence=rule, index=i,
                )
                created.append(b)
                _log_attempt(user, resource, s, e, BookingAttempt.Outcome.BOOKED)
            except (SlotConflict, RuleViolation) as exc:
                reason = exc.details.get("label") if isinstance(exc, SlotConflict) else exc.message
                skipped.append({"index": i, "start": s.isoformat(), "end": e.isoformat(), "code": exc.code, "reason": reason or exc.message})
                _log_attempt(
                    user, resource, s, e,
                    BookingAttempt.Outcome.CONFLICT if isinstance(exc, SlotConflict) else BookingAttempt.Outcome.RULE,
                    exc.code,
                )
        if conflict_policy == RecurrenceRule.ConflictPolicy.ABORT and skipped:
            transaction.set_rollback(True)
            raise BookingError(
                "series_conflict",
                f"{len(skipped)} of {len(occurrences)} dates are unavailable — nothing was booked.",
                {"skipped": skipped},
                http_status=409,
            )
        if not created:
            transaction.set_rollback(True)
            raise BookingError("series_empty", "None of the requested dates are available.", {"skipped": skipped}, http_status=409)
        rule.skipped = skipped
        rule.save(update_fields=["skipped"])

    notify(
        user,
        Notification.Kind.CONFIRMED,
        f"Series booked: {resource.name}",
        f"{len(created)} of {len(occurrences)} dates reserved." + (f" {len(skipped)} skipped due to conflicts." if skipped else ""),
        booking=created[0],
        link=f"/bookings/{created[0].id}",
    )
    return rule, created, skipped


# ---------------------------------------------------------------- lifecycle


def _tell_watchers(booking):
    """The slot just opened up: tell everyone who asked, once. First to book it wins, as with any booking."""
    now = timezone.now()
    if booking.end <= now:
        return
    watches = (
        SlotWatch.objects.filter(resource=booking.resource, notified_at=None, start__lt=booking.end, end__gt=booking.start)
        .exclude(user=booking.user)
        .select_related("user")
    )
    for w in watches:
        notify(
            w.user,
            Notification.Kind.INFO,
            f"A slot just opened: {booking.resource.name}",
            f"{timezone.localtime(booking.start):%a %d %b, %H:%M}–{timezone.localtime(booking.end):%H:%M} is free. "
            "First to book it gets it.",
            link=f"/resources/{booking.resource_id}",
            email=False,
        )
    watches.update(notified_at=now)


def _free_slot(booking):
    BookingSlot.objects.filter(booking=booking).delete()
    _tell_watchers(booking)


def set_status(booking, status, note=""):
    booking.status = status
    booking.status_note = note[:240]
    booking.decided_at = timezone.now()
    booking.save(update_fields=["status", "status_note", "decided_at"])
    if status not in Booking.ACTIVE:
        _free_slot(booking)
        booking.approvals.filter(status__in=["waiting", "pending"]).update(status="cancelled")


def cancel(booking, by, reason=""):
    if not booking.is_active:
        raise BookingError("not_active", "This booking is no longer active.")
    if booking.user_id != by.pk and not by.is_manager:
        raise BookingError("forbidden", "You can only cancel your own bookings.", http_status=403)
    with transaction.atomic():
        set_status(booking, Booking.Status.CANCELLED, reason or f"Cancelled by {by}")
    return booking


def check_in(booking, by, token, now=None):
    """
    Two verification paths:
      * the booker scans the QR poster fixed at the resource (resource.checkin_token) — proves presence
      * a custodian scans the booker's pass (booking.qr_token)
    """
    now = now or timezone.now()
    policy = Policy.get()
    token = str(token).strip()
    if token == str(booking.resource.checkin_token):
        if booking.user_id != by.pk:
            raise BookingError("forbidden", "Only the person who booked can check in with the room code.", http_status=403)
        method = CheckIn.Method.RESOURCE_QR
    elif token == str(booking.qr_token):
        if not by.is_manager and booking.user_id != by.pk:
            raise BookingError("forbidden", "Only custodians can scan booking passes.", http_status=403)
        method = CheckIn.Method.BOOKING_QR if by.pk != booking.user_id else CheckIn.Method.MANUAL
    else:
        raise BookingError("bad_token", "This QR code doesn't belong to this booking's resource.")

    if booking.status == Booking.Status.CHECKED_IN:
        raise BookingError("already_checked_in", "Already checked in.")
    if booking.status != Booking.Status.CONFIRMED:
        raise BookingError("not_confirmed", f"Booking is {booking.get_status_display().lower()}.")
    opens = booking.start - timedelta(minutes=policy.checkin_open_minutes)
    closes = booking.start + timedelta(minutes=policy.grace_minutes)
    if now < opens:
        raise BookingError("too_early", f"Check-in opens at {timezone.localtime(opens):%H:%M}.", {"opens_at": opens.isoformat()})
    if now > closes:
        raise BookingError("too_late", "The grace period has passed — this booking was released.")
    with transaction.atomic():
        CheckIn.objects.create(booking=booking, method=method, verified_by=by)
        booking.status = Booking.Status.CHECKED_IN
        booking.save(update_fields=["status"])
    return booking


def check_in_by_resource_token(user, resource_token, now=None):
    """Mobile flow: scan the room poster, we find *your* booking for that room right now."""
    now = now or timezone.now()
    policy = Policy.get()
    window = Q(period__startswith__lte=now + timedelta(minutes=policy.checkin_open_minutes)) & Q(
        period__startswith__gte=now - timedelta(minutes=policy.grace_minutes)
    )
    booking = (
        Booking.objects.select_related("resource")
        .filter(window, user=user, resource__checkin_token=resource_token, status=Booking.Status.CONFIRMED)
        .order_by("period")
        .first()
    )
    if not booking:
        raise BookingError("no_booking_here", "You have no booking at this resource that can be checked in right now.", http_status=404)
    return check_in(booking, user, resource_token, now)


def check_out(booking, by, note="", now=None):
    """Finish early and hand the remaining time back to the pool."""
    now = now or timezone.now()
    if booking.status != Booking.Status.CHECKED_IN:
        raise BookingError("not_checked_in", "Only a checked-in booking can be checked out.")
    if booking.user_id != by.pk and not by.is_manager:
        raise BookingError("forbidden", "Not your booking.", http_status=403)
    with transaction.atomic():
        end = min(max(now, booking.start + timedelta(minutes=1)), booking.end)
        booking.period = tsrange(booking.start, end)
        booking.status = Booking.Status.COMPLETED
        booking.save(update_fields=["period", "status"])
        _free_slot(booking)
        CheckIn.objects.filter(booking=booking).update(checked_out_at=now, condition_note=note[:240])
    return booking


# ---------------------------------------------------------------- sweeps (Celery Beat / run_scheduler)


def apply_noshow_restriction(user, policy=None):
    policy = policy or Policy.get()
    since = timezone.now() - timedelta(days=policy.noshow_window_days)
    strikes = NoShow.objects.filter(user=user, waived=False, recorded_at__gte=since).count()
    days = 0
    if strikes >= policy.strike_level2:
        days = policy.restrict_days_level2
    elif strikes >= policy.strike_level1:
        days = policy.restrict_days_level1
    if days:
        until = timezone.now() + timedelta(days=days)
        if not user.restricted_until or user.restricted_until < until:
            user.restricted_until = until
            user.restriction_reason = f"{strikes} no-shows in {policy.noshow_window_days} days"
            user.save(update_fields=["restricted_until", "restriction_reason"])
            notify(
                user, Notification.Kind.RESTRICTED, "Booking paused",
                f"You missed {strikes} bookings in the last {policy.noshow_window_days} days. "
                f"New bookings are paused for {days} days.",
                link="/me",
            )
    elif strikes >= policy.strike_warn:
        notify(
            user, Notification.Kind.RESTRICTED, "No-show warning",
            f"{strikes} missed check-ins. At {policy.strike_level1} your booking rights pause for {policy.restrict_days_level1} days.",
            link="/me", email=False,
        )
    return strikes


def auto_release_sweep(now=None):
    """Release confirmed bookings nobody checked into within the grace period."""
    now = now or timezone.now()
    policy = Policy.get()
    cutoff = now - timedelta(minutes=policy.grace_minutes)
    released = 0
    due = Booking.objects.select_related("resource__type", "user").filter(
        status=Booking.Status.CONFIRMED, resource__type__requires_checkin=True, period__startswith__lt=cutoff
    )
    for booking in due:
        with transaction.atomic():
            locked = Booking.objects.select_for_update(skip_locked=True).filter(pk=booking.pk, status=Booking.Status.CONFIRMED).first()
            if not locked:
                continue
            set_status(locked, Booking.Status.RELEASED, f"Not checked in within {policy.grace_minutes} min")
            # Shared demo personas must stay bookable however long the app runs unattended.
            strike = not (settings.DEMO_MODE and locked.user.username.startswith("demo."))
            if strike:
                NoShow.objects.get_or_create(booking=locked, defaults={"user": locked.user, "resource": locked.resource})
            notify(
                locked.user, Notification.Kind.RELEASED, f"Released: {locked.resource.name}",
                f"You didn't check in by {timezone.localtime(locked.start + timedelta(minutes=policy.grace_minutes)):%H:%M}, "
                "so the slot was released for others.",
                booking=locked, link=f"/bookings/{locked.id}",
            )
            if strike:
                apply_noshow_restriction(locked.user, policy)
            released += 1

    # Pending requests nobody decided before the start time expire.
    for b in Booking.objects.filter(status=Booking.Status.PENDING, period__startswith__lt=now):
        with transaction.atomic():
            set_status(b, Booking.Status.REJECTED, "Expired — not approved before start time")
            notify(b.user, Notification.Kind.REJECTED, f"Request expired: {b.resource.name}", "It wasn't approved in time.", booking=b)
    return released


def complete_finished(now=None):
    now = now or timezone.now()
    done = 0
    for b in Booking.objects.select_related("resource__type").filter(
        Q(status=Booking.Status.CHECKED_IN) | Q(status=Booking.Status.CONFIRMED, resource__type__requires_checkin=False),
        period__endswith__lte=now,
    ):
        with transaction.atomic():
            b.status = Booking.Status.COMPLETED
            b.save(update_fields=["status"])
            _free_slot(b)
            CheckIn.objects.filter(booking=b, checked_out_at__isnull=True).update(checked_out_at=b.end)
            done += 1
    return done


def send_reminders(now=None):
    now = now or timezone.now()
    policy = Policy.get()
    soon = now + timedelta(minutes=policy.reminder_minutes)
    sent = 0
    for b in Booking.objects.select_related("resource", "user").filter(
        status=Booking.Status.CONFIRMED, reminder_sent=False, period__startswith__gt=now, period__startswith__lte=soon
    ):
        kind = Notification.Kind.CHECKIN_REQUIRED if b.resource.type.requires_checkin else Notification.Kind.REMINDER
        notify(
            b.user, kind, f"Starting soon: {b.resource.name}",
            f"{timezone.localtime(b.start):%H:%M} at {b.resource.location or b.resource.name}. "
            + (f"Scan the room QR within {policy.grace_minutes} min of start or it will be released." if b.resource.type.requires_checkin else ""),
            booking=b, link=f"/bookings/{b.id}",
        )
        b.reminder_sent = True
        b.save(update_fields=["reminder_sent"])
        sent += 1
    return sent


# ---------------------------------------------------------------- displacement (timetable / maintenance)


def displace(resource, start, end, reason, kind=Notification.Kind.UNAVAILABLE):
    """Free every live booking overlapping [start, end) so a higher-priority occupancy can claim it."""
    hit = list(
        Booking.objects.select_for_update()
        .filter(resource=resource, status__in=Booking.ACTIVE, period__overlap=(start, end))
        .select_related("user")
    )
    for b in hit:
        set_status(b, Booking.Status.DISPLACED, reason)
        notify(
            b.user, kind, f"Booking moved off: {resource.name}",
            f"Your booking on {timezone.localtime(b.start):%a %d %b %H:%M} was cancelled — {reason}. "
            "Sorry! Pick another slot from the calendar.",
            booking=b, link=f"/resources/{resource.id}",
        )
    return len(hit)
