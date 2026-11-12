"""
Faculty tools: their teaching week, and finding a make-up class slot that suits the section, the
teacher and a free classroom all at once.
"""
from datetime import datetime, time, timedelta

from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.bookings.exceptions import BookingError
from apps.bookings.models import Booking, BookingSlot
from apps.rules.services import blackouts_for, merge, open_windows, rules_for, subtract
from apps.timetable.models import TimetableEntry

from .models import Resource

HORIZON_DAYS = 7
STEP = timedelta(minutes=30)
PER_DAY = 3
MAX_OPTIONS = 12


def _staff_only(user):
    if not user.can_book_recurring:
        raise BookingError("staff_only", "This is for teaching staff.", http_status=403)


def _current_entries():
    return TimetableEntry.objects.filter(version__is_current=True).select_related("resource__location", "version")


def _mine(entries, user):
    """Timetable rows taught by this user. The timetable names teachers, e.g. "Dr. Meera Iyer"."""
    name = user.get_full_name().strip()
    return entries.filter(faculty_name__icontains=name) if name else entries.none()


def _occurrences(entries, first, last):
    """Each weekly timetable row as dated (start, end, entry) between two local dates."""
    tz = timezone.get_current_timezone()
    out = []
    day = first
    while day <= last:
        for e in entries:
            if e.weekday == day.weekday() and e.version.term_start <= day <= e.version.term_end:
                out.append((
                    timezone.make_aware(datetime.combine(day, e.start_time), tz),
                    timezone.make_aware(datetime.combine(day, e.end_time), tz),
                    e,
                ))
        day += timedelta(days=1)
    return out


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def teaching_week(request):
    """The next seven days for a teacher: timetabled classes and their own bookings, in time order."""
    user = request.user
    _staff_only(user)
    today = timezone.localdate()
    last = today + timedelta(days=HORIZON_DAYS - 1)
    entries = list(_mine(_current_entries(), user))
    items = [
        {"kind": "class", "start": s, "end": e, "title": f"{x.course_code} · {x.section}" if x.section else x.course_code,
         "subtitle": x.course_name, "section": x.section, "room": {"id": x.resource_id, "name": x.resource.name}}
        for s, e, x in _occurrences(entries, today, last)
    ]
    tz = timezone.get_current_timezone()
    lo = timezone.make_aware(datetime.combine(today, time(0)), tz)
    for b in Booking.objects.filter(user=user, status__in=Booking.ACTIVE, period__overlap=(lo, lo + timedelta(days=HORIZON_DAYS))).select_related("resource"):
        items.append({"kind": "booking", "start": b.start, "end": b.end, "title": b.title, "subtitle": b.get_status_display(),
                      "section": b.on_behalf_of, "room": {"id": b.resource_id, "name": b.resource.name}, "booking": b.id})
    items.sort(key=lambda i: i["start"])
    mine = sorted({x.section for x in entries if x.section})
    every = sorted(set(_current_entries().exclude(section="").values_list("section", flat=True)))
    return Response({"items": items, "my_sections": mine, "all_sections": every, "matched_timetable": bool(entries)})


def find_makeup_slots(user, section, minutes, size, now=None):
    """
    Times in the next week when the section has no class, the teacher is free, and a classroom big
    enough is open and empty. Spread out over the days, smallest fitting room first.
    """
    now = now or timezone.now()
    tz = timezone.get_current_timezone()
    first = timezone.localdate(now)
    last = first + timedelta(days=HORIZON_DAYS)
    lo = timezone.make_aware(datetime.combine(first, time(0)), tz)
    hi = lo + timedelta(days=HORIZON_DAYS + 1)
    length = timedelta(minutes=minutes)
    earliest = now + timedelta(hours=1)

    current = _current_entries()
    section_busy = [(s, e) for s, e, _ in _occurrences(current.filter(section__iexact=section), first, last)]
    section_busy += [(b.start, b.end) for b in Booking.objects.filter(on_behalf_of__iexact=section, status__in=Booking.ACTIVE, period__overlap=(lo, hi))]
    teacher_busy = [(s, e) for s, e, _ in _occurrences(_mine(current, user), first, last)]
    teacher_busy += [(b.start, b.end) for b in Booking.objects.filter(user=user, status__in=Booking.ACTIVE, period__overlap=(lo, hi))]
    blocked = merge(section_busy + teacher_busy)

    rooms = list(
        Resource.objects.filter(type__name="Classroom", status=Resource.Status.ACTIVE, capacity__gte=size)
        .select_related("type", "location").order_by("capacity", "name")
    )
    taken = {}
    for s in BookingSlot.objects.filter(resource__in=rooms, period__overlap=(lo, hi)).only("resource_id", "period"):
        taken.setdefault(s.resource_id, []).append((s.period.lower, s.period.upper))
    free = {
        r.id: subtract(open_windows(r, first, last + timedelta(days=1), rules_for(r)),
                       taken.get(r.id, []) + [(b.period.lower, b.period.upper) for b in blackouts_for(r, lo, hi)])
        for r in rooms
    }

    def fits(intervals, s, e):
        return any(a <= s and e <= b for a, b in intervals)

    def clashes(s, e):
        return any(a < e and s < b for a, b in blocked)

    options, per_day, last_pick = [], {}, {}
    cursor = lo + timedelta(hours=8)
    while cursor + length <= hi and len(options) < MAX_OPTIONS:
        s, e = cursor, cursor + length
        day = timezone.localtime(s).date()
        cursor += STEP
        if s < earliest or per_day.get(day, 0) >= PER_DAY or clashes(s, e):
            continue
        # Spread the suggestions out: at least 90 minutes apart on the same day.
        if day in last_pick and s - last_pick[day] < timedelta(minutes=90):
            continue
        fitting = [r for r in rooms if fits(free[r.id], s, e)]
        if not fitting:
            continue
        r = fitting[0]
        options.append({
            "start": s, "end": e, "others": len(fitting) - 1,
            "room": {"id": r.id, "name": r.name, "code": r.code, "capacity": r.capacity,
                     "location_label": str(r.location) if r.location else None},
        })
        per_day[day] = per_day.get(day, 0) + 1
        last_pick[day] = s
    return options


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def makeup_slots(request):
    _staff_only(request.user)
    section = str(request.query_params.get("section", "")).strip()
    if not section:
        raise BookingError("no_section", "Pick the section the make-up class is for.")
    try:
        minutes = min(max(int(request.query_params.get("minutes", 50)), 30), 180)
        size = min(max(int(request.query_params.get("size", 40)), 1), 500)
    except ValueError:
        raise BookingError("bad_number", "Length and class size must be numbers.")
    return Response({"section": section, "minutes": minutes, "size": size,
                     "options": find_makeup_slots(request.user, section, minutes, size)})
