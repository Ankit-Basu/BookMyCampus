from datetime import timedelta

from django.core.cache import cache
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.accounts.models import Role
from apps.accounts.permissions import IsManager

from . import services


def _range(request, default_days=30):
    today = timezone.localdate()
    end = parse_date(request.query_params.get("to", "") or "") or today + timedelta(days=1)
    start = parse_date(request.query_params.get("from", "") or "") or end - timedelta(days=default_days)
    return start, end


def _dept_scope(request):
    """Department heads see their own department; managers above see everything."""
    u = request.user
    if u.role == Role.DEPT_HEAD and u.department_id:
        return u.department_id
    return request.query_params.get("department") or None


@api_view(["GET"])
@permission_classes([IsManager])
def utilisation(request):
    s, e = _range(request)
    return Response(services.utilisation_report(s, e, request.query_params.get("type"), _dept_scope(request)))


@api_view(["GET"])
@permission_classes([IsManager])
def heatmap(request):
    s, e = _range(request, 28)
    return Response(services.heatmap(s, e, request.query_params.get("type")))


@api_view(["GET"])
@permission_classes([IsManager])
def noshows(request):
    s, e = _range(request)
    return Response(services.noshow_report(s, e))


@api_view(["GET"])
@permission_classes([IsManager])
def demand(request):
    s, e = _range(request)
    return Response(services.demand_vs_supply(s, e))


@api_view(["GET"])
@permission_classes([IsManager])
def approvals(request):
    s, e = _range(request)
    return Response(services.approval_turnaround(s, e))


@api_view(["GET"])
@permission_classes([IsManager])
def downtime(request):
    s, e = _range(request)
    return Response(services.maintenance_downtime(s, e))


@api_view(["GET"])
@permission_classes([IsManager])
def quotas(request):
    return Response(services.quota_consumption())


@api_view(["GET"])
@permission_classes([IsManager])
def dashboard(request):
    return Response(services.dashboard(request.user))


@api_view(["GET"])
@permission_classes([AllowAny])
def public_stats(request):
    """Headline numbers for the public landing page. Cached — the idle ranking is not cheap."""
    data = cache.get("public_stats")
    if data:
        return Response(data)
    from django.db.models import Count, Q

    from apps.bookings.models import Booking, BookingAttempt
    from apps.catalogue.models import Resource, ResourceType

    today = timezone.localdate()
    month_ago = timezone.now() - timedelta(days=30)
    report = services.utilisation_report(today - timedelta(days=28), today + timedelta(days=1))
    idle = report["idle_ranking"][0] if report["idle_ranking"] else None
    types = []
    for t in ResourceType.objects.annotate(n=Count("resources", filter=~Q(resources__status="retired"))).order_by("name"):
        r = Resource.objects.filter(type=t).exclude(image_url="").first()
        types.append({"name": t.name, "slug": t.slug, "color": t.color, "icon": t.icon, "count": t.n,
                      "description": t.description, "cover": r.cover if r else ""})
    data = {
        "resources": Resource.objects.exclude(status="retired").count(),
        "types": types,
        "bookings_30d": Booking.objects.filter(period__startswith__gte=month_ago).count(),
        "conflicts_blocked": BookingAttempt.objects.filter(outcome="conflict").count(),
        "double_bookings": 0,
        "utilisation": report["totals"]["utilisation"],
        "idle_value_inr": report["totals"]["idle_value_inr"],
        "idle_top": idle and {k: idle[k] for k in ("name", "code", "value_inr", "utilisation", "image", "type")},
        "names": list(Resource.objects.exclude(status="retired").order_by("?").values_list("name", flat=True)[:14]),
    }
    cache.set("public_stats", data, 300)
    return Response(data)


@api_view(["GET"])
@permission_classes([IsManager])
def system_health(request):
    """What's running: database, sweeper heartbeat, Redis, email transport, realtime, timetable."""
    from django.conf import settings
    from django.db import connection

    from apps.rules.models import Policy
    from apps.timetable.models import TimetableVersion

    db_ok = True
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
    except Exception:
        db_ok = False
    redis_ok = False
    try:
        import redis

        redis_ok = bool(redis.Redis.from_url(settings.CELERY_BROKER_URL, socket_connect_timeout=0.3).ping())
    except Exception:
        pass
    last = Policy.get().last_sweep_at
    age = (timezone.now() - last).total_seconds() if last else None
    tt = TimetableVersion.objects.filter(is_current=True).first()
    backend = settings.EMAIL_BACKEND.rsplit(".", 2)[-2]
    return Response({
        "database": db_ok,
        "redis": redis_ok,
        "sweeper": {"last_run": last, "age_seconds": age, "healthy": age is not None and age < 180},
        "email": {"backend": backend, "live": backend == "smtp"},
        "realtime": "sse",
        "timetable": tt and {"label": tt.label, "published_at": tt.published_at},
    })
