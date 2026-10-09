"""
Availability engine: opening hours, booking windows, duration and lead-time limits, blackouts,
role permissions, quotas and no-show restriction. Everything here is *policy* — it decides what a
user is allowed to ask for. Whether the slot is actually free is decided by the database
(see apps.bookings.services), so policy and correctness never get tangled.
"""
from datetime import datetime, time, timedelta

from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Role
from apps.bookings.exceptions import RuleViolation

from .models import AvailabilityRule, Blackout, Policy, Quota

# ---------------------------------------------------------------- interval helpers


def merge(intervals):
    """Merge overlapping/adjacent (start, end) pairs."""
    out = []
    for s, e in sorted(intervals):
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def subtract(base, cuts):
    """base minus cuts, both lists of (start, end)."""
    result = []
    cuts = merge(cuts)
    for s, e in base:
        cur = s
        for cs, ce in cuts:
            if ce <= cur or cs >= e:
                continue
            if cs > cur:
                result.append((cur, cs))
            cur = max(cur, ce)
            if cur >= e:
                break
        if cur < e:
            result.append((cur, e))
    return result


def total_minutes(intervals):
    return int(sum((e - s).total_seconds() for s, e in intervals) // 60)


# ---------------------------------------------------------------- rules lookup


def rules_for(resource):
    own = list(AvailabilityRule.objects.filter(resource=resource))
    if own:
        return own
    return list(AvailabilityRule.objects.filter(resource_type_id=resource.type_id, resource__isnull=True))


def blackouts_for(resource, start, end):
    return Blackout.objects.filter(period__overlap=(start, end)).filter(
        Q(resource__isnull=True, resource_type__isnull=True) | Q(resource=resource) | Q(resource_type_id=resource.type_id)
    )


def open_windows(resource, day_start, day_end, rules=None):
    """Opening-hours windows (aware datetimes) for every local date in [day_start, day_end)."""
    rules = rules if rules is not None else rules_for(resource)
    tz = timezone.get_current_timezone()
    windows = []
    d = day_start
    while d < day_end:
        for r in rules:
            if d.weekday() in r.weekdays:
                windows.append(
                    (
                        timezone.make_aware(datetime.combine(d, r.open_time), tz),
                        timezone.make_aware(datetime.combine(d, r.close_time), tz),
                    )
                )
        d += timedelta(days=1)
    return merge(windows)


def bookable_windows(resource, start_date, end_date):
    """Opening hours minus blackouts — the supply side used by utilisation analytics."""
    windows = open_windows(resource, start_date, end_date)
    if not windows:
        return []
    lo, hi = windows[0][0], windows[-1][1]
    cuts = [(b.period.lower, b.period.upper) for b in blackouts_for(resource, lo, hi)]
    return subtract(windows, cuts)


def matching_rule(resource, start, end, rules=None):
    """The rule whose opening window fully contains [start, end), or None."""
    rules = rules if rules is not None else rules_for(resource)
    ls, le = timezone.localtime(start), timezone.localtime(end)
    for r in rules:
        if ls.date() != le.date() and not (le.time() == time(0) and le.date() == ls.date() + timedelta(days=1)):
            continue
        if ls.weekday() not in r.weekdays:
            continue
        end_t = le.time() if le.time() != time(0) else time(23, 59, 59)
        if r.open_time <= ls.time() and end_t <= r.close_time:
            return r
    return None


# ---------------------------------------------------------------- validation


def validate_request(user, resource, start, end, attendees=1, now=None, check_quota=True):
    """Raise RuleViolation if the request breaks any policy. Returns the matched rule."""
    now = now or timezone.now()
    if end <= start:
        raise RuleViolation("invalid_period", "End time must be after start time.")
    if resource.status != resource.Status.ACTIVE:
        raise RuleViolation("resource_unavailable", f"{resource.name} is currently out of service.")
    if user.is_restricted:
        raise RuleViolation(
            "user_restricted",
            f"Booking is paused until {timezone.localtime(user.restricted_until):%d %b %H:%M} after repeated no-shows.",
            {"restricted_until": user.restricted_until.isoformat(), "reason": user.restriction_reason},
            http_status=403,
        )
    allowed = resource.type.allowed_roles
    if allowed and user.role not in allowed and not user.is_superuser:
        raise RuleViolation(
            "role_not_permitted",
            f"{resource.type.name} can only be booked by: {', '.join(Role(r).label for r in allowed if r in Role.values)}.",
            http_status=403,
        )
    if attendees > resource.capacity:
        raise RuleViolation("over_capacity", f"{resource.name} holds {resource.capacity}; you asked for {attendees}.")

    rules = rules_for(resource)
    if not rules:
        raise RuleViolation("no_rules", "This resource has no published opening hours yet.")
    rule = matching_rule(resource, start, end, rules)
    if rule is None:
        raise RuleViolation("outside_hours", "That time is outside the resource's opening hours.")

    minutes = (end - start).total_seconds() / 60
    if minutes < rule.min_duration_minutes:
        raise RuleViolation("too_short", f"Minimum booking is {rule.min_duration_minutes} minutes.")
    if minutes > rule.max_duration_minutes:
        raise RuleViolation("too_long", f"Maximum booking is {rule.max_duration_minutes // 60}h {rule.max_duration_minutes % 60:02d}m.")
    if start < now + timedelta(minutes=rule.min_lead_minutes):
        if start < now:
            raise RuleViolation("in_past", "That slot has already started.")
        raise RuleViolation("lead_time", f"Book at least {rule.min_lead_minutes} minutes in advance.")
    if start > now + timedelta(days=rule.max_advance_days):
        raise RuleViolation("beyond_window", f"Bookings open {rule.max_advance_days} days ahead.")

    blackout = blackouts_for(resource, start, end).first()
    if blackout:
        raise RuleViolation("blackout", f"Blocked: {blackout.title}.", {"blackout": blackout.title})

    if check_quota:
        check_quotas(user, resource, start, end)
    return rule


def _week_bounds(dt):
    local = timezone.localtime(dt)
    monday = (local - timedelta(days=local.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday, monday + timedelta(days=7)


def quotas_for(user, resource):
    return Quota.objects.filter(
        Q(department__isnull=True) | Q(department_id=user.department_id),
        Q(role="") | Q(role=user.role),
        Q(resource_type__isnull=True) | Q(resource_type_id=resource.type_id),
    )


def _booked_minutes(qs, ws, we):
    total = 0
    for b in qs.filter(period__overlap=(ws, we)).only("period"):
        s, e = max(b.period.lower, ws), min(b.period.upper, we)
        total += (e - s).total_seconds() / 60
    return total


def check_quotas(user, resource, start, end):
    from apps.bookings.models import Booking

    quotas = list(quotas_for(user, resource))
    if not quotas:
        return
    ws, we = _week_bounds(start)
    req = (end - start).total_seconds() / 60
    live = Booking.objects.filter(status__in=Booking.ACTIVE + (Booking.Status.COMPLETED,))
    for q in quotas:
        scoped = live.filter(resource__type_id=q.resource_type_id) if q.resource_type_id else live
        if q.user_hours_per_week:
            used = _booked_minutes(scoped.filter(user=user), ws, we)
            if used + req > q.user_hours_per_week * 60:
                raise RuleViolation(
                    "quota_user",
                    f"Weekly limit reached: {q.user_hours_per_week}h per person ({used / 60:.1f}h used).",
                    {"used_hours": round(used / 60, 1), "limit_hours": q.user_hours_per_week},
                )
        if q.department_hours_per_week and user.department_id:
            used = _booked_minutes(scoped.filter(user__department_id=user.department_id), ws, we)
            if used + req > q.department_hours_per_week * 60:
                raise RuleViolation(
                    "quota_department",
                    f"Your department has used {used / 60:.1f}h of its {q.department_hours_per_week}h weekly quota.",
                    {"used_hours": round(used / 60, 1), "limit_hours": q.department_hours_per_week},
                )
        if q.max_active_bookings:
            active = scoped.filter(user=user, status__in=Booking.ACTIVE, period__endswith__gt=timezone.now()).count()
            if active >= q.max_active_bookings:
                raise RuleViolation(
                    "quota_active", f"You can hold at most {q.max_active_bookings} upcoming bookings of this kind."
                )


# ---------------------------------------------------------------- availability view


def availability(resource, start_date, end_date, viewer=None):
    """
    Day-by-day picture for the calendar: opening windows, every busy block from the occupancy
    ledger (bookings, timetabled classes, maintenance), blackouts, and the free bookable slots.
    Timetabled classes come straight out of the ledger, so a room teaching at 10:00 is never
    offered at 10:00.
    """
    from apps.bookings.models import BookingSlot

    rules = rules_for(resource)
    windows = open_windows(resource, start_date, end_date, rules)
    tz = timezone.get_current_timezone()
    lo = timezone.make_aware(datetime.combine(start_date, time(0)), tz)
    hi = timezone.make_aware(datetime.combine(end_date, time(0)), tz)

    busy = []
    for s in (
        BookingSlot.objects.filter(resource=resource, period__overlap=(lo, hi))
        .select_related("booking__user", "timetable_entry", "maintenance")
        .order_by("period")
    ):
        item = {"start": s.period.lower, "end": s.period.upper, "kind": s.kind, "label": s.label}
        if s.booking_id:
            b = s.booking
            mine = viewer is not None and b.user_id == viewer.pk
            item.update(
                booking_id=b.id if (mine or (viewer and viewer.is_manager)) else None,
                status=b.status,
                mine=mine,
                label=b.title if (mine or (viewer and viewer.is_manager)) else "Booked",
            )
        busy.append(item)

    blackout_iv = [(b.period.lower, b.period.upper, b.title) for b in blackouts_for(resource, lo, hi)]
    now = timezone.now()
    slot_minutes = min((r.slot_minutes for r in rules), default=30)
    free = subtract(windows, [(b["start"], b["end"]) for b in busy] + [(s, e) for s, e, _ in blackout_iv] + [(lo, now)])
    # Snap free intervals to the slot grid so the UI offers clean, bookable chunks.
    slots = []
    step = timedelta(minutes=slot_minutes)
    for s, e in free:
        local = timezone.localtime(s)
        offset = (local.minute % slot_minutes) * 60 + local.second
        cur = s + timedelta(seconds=(slot_minutes * 60 - offset) % (slot_minutes * 60)) if offset else s
        while cur + step <= e:
            slots.append({"start": cur, "end": cur + step})
            cur += step

    return {
        "resource": resource.id,
        "slot_minutes": slot_minutes,
        "rules": [
            {
                "weekdays": r.weekdays,
                "open": r.open_time.strftime("%H:%M"),
                "close": r.close_time.strftime("%H:%M"),
                "min_duration": r.min_duration_minutes,
                "max_duration": r.max_duration_minutes,
                "min_lead": r.min_lead_minutes,
                "max_advance_days": r.max_advance_days,
            }
            for r in rules
        ],
        "open": [{"start": s, "end": e} for s, e in windows],
        "busy": busy,
        "blackouts": [{"start": s, "end": e, "title": t} for s, e, t in blackout_iv],
        "free": slots,
        "policy": {"grace_minutes": Policy.get().grace_minutes},
    }
