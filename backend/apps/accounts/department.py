"""
HOD tools for their own department: who is teaching how much, which students need a word, and
sending everyone a notice.
"""
from datetime import timedelta

from django.db.models import Count, Q
from django.utils import timezone
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.bookings.exceptions import BookingError
from apps.bookings.models import Booking, NoShow
from apps.notifications.models import Notification
from apps.notifications.services import notify
from apps.timetable.models import TimetableEntry

from .models import Department, DepartmentNotice, Role, User
from .permissions import IsManager

TEACHING = [Role.FACULTY, Role.DEPT_HEAD]
NOTICES_PER_DAY = 10


def _department(request):
    """The HOD's own department. Facility managers and admins can look at any with ?department=CODE."""
    user = request.user
    code = request.query_params.get("department") or request.data.get("department")
    if code and user.role in (Role.FACILITY_MANAGER, Role.ADMIN):
        dept = Department.objects.filter(code=code).first()
    else:
        dept = user.department
    if dept is None:
        raise BookingError("no_department", "Your account isn't in a department.")
    return dept


@api_view(["GET"])
@permission_classes([IsManager])
def overview(request):
    dept = _department(request)
    now = timezone.now()
    month_ago, week_ahead = now - timedelta(days=30), now + timedelta(days=7)
    entries = list(TimetableEntry.objects.filter(version__is_current=True).only("faculty_name", "start_time", "end_time"))

    faculty = []
    for u in User.objects.filter(department=dept, role__in=TEACHING, is_active=True).order_by("first_name"):
        name = u.get_full_name().strip()
        mine = [e for e in entries if name and name.lower() in e.faculty_name.lower()]
        minutes = sum((e.end_time.hour * 60 + e.end_time.minute) - (e.start_time.hour * 60 + e.start_time.minute) for e in mine)
        bookings = Booking.objects.filter(user=u)
        faculty.append({
            "id": u.id, "name": name or u.username, "role": u.role,
            "classes_per_week": len(mine), "teaching_hours": round(minutes / 60, 1),
            "upcoming_bookings": bookings.filter(status__in=Booking.ACTIVE, period__overlap=(now, week_ahead)).count(),
            "makeups_30d": bookings.exclude(on_behalf_of="").filter(
                status__in=[*Booking.ACTIVE, Booking.Status.COMPLETED], period__overlap=(month_ago, week_ahead)).count(),
            "noshows_30d": NoShow.objects.filter(user=u, waived=False, recorded_at__gte=month_ago).count(),
        })

    students = User.objects.filter(department=dept, role=Role.STUDENT, is_active=True)
    flagged = (
        students.annotate(recent=Count("noshows", filter=Q(noshows__waived=False, noshows__recorded_at__gte=month_ago)))
        .filter(Q(recent__gt=0) | Q(restricted_until__gt=now))
        .order_by("-recent", "first_name")[:20]
    )
    members = User.objects.filter(department=dept, is_active=True)
    return Response({
        "department": {"code": dept.code, "name": dept.name},
        "counts": {
            "faculty": len(faculty),
            "students": students.count(),
            "bookings_this_week": Booking.objects.filter(user__in=members, status__in=Booking.ACTIVE, period__overlap=(now, week_ahead)).count(),
            "noshows_30d": NoShow.objects.filter(user__in=members, waived=False, recorded_at__gte=month_ago).count(),
        },
        "faculty": faculty,
        "students_to_watch": [
            {"id": s.id, "name": s.get_full_name() or s.username, "username": s.username, "noshows_30d": s.recent,
             "restricted_until": s.restricted_until if s.is_restricted else None}
            for s in flagged
        ],
    })


def _notice_json(n):
    return {"id": n.id, "audience": n.audience, "audience_label": n.get_audience_display(), "title": n.title, "body": n.body,
            "recipients": n.recipients, "author": n.author.get_full_name() if n.author else None, "created_at": n.created_at}


@api_view(["GET", "POST"])
@permission_classes([IsManager])
def notices(request):
    """List the department's notices, or send one. Each recipient gets an in-app notification."""
    dept = _department(request)
    if request.method == "GET":
        return Response([_notice_json(n) for n in DepartmentNotice.objects.filter(department=dept).select_related("author")[:20]])

    title = str(request.data.get("title", "")).strip()[:120]
    body = str(request.data.get("body", "")).strip()[:500]
    audience = request.data.get("audience", DepartmentNotice.Audience.EVERYONE)
    if not title:
        raise BookingError("no_title", "Give the notice a title.")
    if audience not in DepartmentNotice.Audience.values:
        raise BookingError("bad_audience", "Choose who the notice is for.")
    if DepartmentNotice.objects.filter(author=request.user, created_at__gte=timezone.now() - timedelta(days=1)).count() >= NOTICES_PER_DAY:
        raise BookingError("too_many_requests", "You've sent 10 notices in the last day.", http_status=429)

    people = User.objects.filter(department=dept, is_active=True).exclude(pk=request.user.pk)
    if audience == DepartmentNotice.Audience.FACULTY:
        people = people.filter(role__in=TEACHING)
    elif audience == DepartmentNotice.Audience.STUDENTS:
        people = people.filter(role=Role.STUDENT)
    people = list(people)
    sender = request.user.get_full_name() or request.user.username
    for p in people:
        notify(p, Notification.Kind.INFO, f"{dept.code}: {title}", f"{body} — {sender}" if body else f"From {sender}", email=False)
    n = DepartmentNotice.objects.create(department=dept, author=request.user, audience=audience, title=title, body=body, recipients=len(people))
    return Response(_notice_json(n), status=201)
