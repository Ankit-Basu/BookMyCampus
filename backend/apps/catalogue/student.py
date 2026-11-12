"""
Things students need beyond booking: finding an empty room to sit and study in, and asking a teacher
to book a lab or classroom, since only staff can book those.
"""
from datetime import timedelta

from django.core.cache import cache
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Role, User
from apps.bookings.exceptions import BookingError
from apps.bookings.models import BookingSlot
from apps.notifications.models import Notification
from apps.notifications.services import notify
from apps.rules.services import blackouts_for, open_windows, rules_for, subtract

from .models import Resource

STUDY_TYPES = ["Classroom", "Laboratory"]
MIN_STUDY_MINUTES = 20
SOON_MINUTES = 60
TEACHER_ROLES = [Role.FACULTY, Role.DEPT_HEAD]
ASKS_PER_DAY = 10


def _spot(r, **extra):
    return {
        "id": r.id, "code": r.code, "name": r.name, "type_name": r.type.name, "type_icon": r.type.icon,
        "type_color": r.type.color, "building": r.location.building if r.location else None,
        "location_label": str(r.location) if r.location else None, "capacity": r.capacity,
        "features": r.features[:3], **extra,
    }


def study_spots_at(at):
    """Classrooms and labs with nothing on at `at`: no class, booking, maintenance or blackout, and open."""
    tz = timezone.get_current_timezone()
    day = timezone.localtime(at, tz).date()
    lo = timezone.make_aware(timezone.datetime.combine(day, timezone.datetime.min.time()), tz)
    hi = lo + timedelta(days=1)
    rooms = list(
        Resource.objects.filter(type__name__in=STUDY_TYPES, status=Resource.Status.ACTIVE)
        .select_related("type", "location").order_by("name")
    )
    busy = {}
    for s in BookingSlot.objects.filter(resource__in=rooms, period__overlap=(lo, hi)).only("resource_id", "period"):
        busy.setdefault(s.resource_id, []).append((s.period.lower, s.period.upper))

    free_now, soon = [], []
    for r in rooms:
        cuts = busy.get(r.id, []) + [(b.period.lower, b.period.upper) for b in blackouts_for(r, lo, hi)]
        for start, end in subtract(open_windows(r, day, day + timedelta(days=1), rules_for(r)), cuts):
            if start <= at < end:
                minutes = int((end - at).total_seconds() // 60)
                if minutes >= MIN_STUDY_MINUTES:
                    free_now.append(_spot(r, free_until=end, minutes=minutes))
                break
            if at < start <= at + timedelta(minutes=SOON_MINUTES) and (end - start) >= timedelta(minutes=MIN_STUDY_MINUTES):
                soon.append(_spot(r, free_from=start, free_until=end, minutes=int((end - start).total_seconds() // 60)))
                break
    free_now.sort(key=lambda s: -s["minutes"])
    soon.sort(key=lambda s: s["free_from"])
    return free_now, soon


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def study_spots(request):
    """Empty rooms to sit and study in, now or at a chosen time in the next week."""
    now = timezone.now()
    at = parse_datetime(request.query_params.get("at", "")) or now
    if timezone.is_naive(at):
        at = timezone.make_aware(at)
    at = min(max(at, now), now + timedelta(days=7))
    free_now, soon = study_spots_at(at)
    return Response({"at": at, "free": free_now, "soon": soon})


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def teachers(request):
    """Faculty a student can ask to book a room: their own department first, then everyone else."""
    qs = User.objects.filter(role__in=TEACHER_ROLES, is_active=True).select_related("department")
    mine = request.user.department_id
    people = sorted(qs, key=lambda u: (u.department_id != mine, u.get_full_name() or u.username))
    return Response([
        {"id": u.id, "name": u.get_full_name() or u.username, "department": u.department.code if u.department else None,
         "same_department": bool(mine) and u.department_id == mine, "role": u.role}
        for u in people
    ])


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def ask_teacher(request, pk):
    """A student asks a teacher to book a staff-only room for them. The teacher gets a ready-made link."""
    resource = get_object_or_404(Resource.objects.select_related("type"), pk=pk)
    user = request.user
    teacher = User.objects.filter(pk=request.data.get("teacher"), role__in=TEACHER_ROLES, is_active=True).first()
    if teacher is None:
        raise BookingError("bad_teacher", "Pick a teacher to ask.")
    start, end = parse_datetime(str(request.data.get("start", ""))), parse_datetime(str(request.data.get("end", "")))
    if not start or not end or end <= start:
        raise BookingError("invalid_period", "Pick a start and an end time.")
    if start <= timezone.now():
        raise BookingError("slot_passed", "That time has already passed.")
    if end - start > timedelta(hours=4):
        raise BookingError("too_long", "Ask for 4 hours or less.")
    note = str(request.data.get("note", "")).strip()[:300]

    key = f"ask-teacher:{user.pk}:{timezone.localdate()}"
    sent = cache.get(key, 0)
    if sent >= ASKS_PER_DAY:
        raise BookingError("too_many_requests", "You've sent today's 10 requests. Try again tomorrow.", http_status=429)
    cache.set(key, sent + 1, 60 * 60 * 24)

    who = user.get_full_name() or user.username
    local = timezone.localtime(start)
    when = f"{local:%a %d %b}, {local:%H:%M}–{timezone.localtime(end):%H:%M}"
    query = f"start={start.isoformat().replace('+', '%2B')}&end={end.isoformat().replace('+', '%2B')}"
    notify(
        teacher, Notification.Kind.INFO, f"{who} asks you to book {resource.name}",
        f"{when}." + (f" “{note}”" if note else "") + (f" Registration no. {user.username}." if user.username.isdigit() else ""),
        link=f"/resources/{resource.id}?{query}",
    )
    return Response({"sent_to": teacher.get_full_name() or teacher.username}, status=201)
