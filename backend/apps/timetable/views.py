import hmac

from django.conf import settings
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.accounts.permissions import IsPolicyAdmin

from . import services
from .models import TimetableEntry, TimetableVersion


class VersionSerializer(serializers.ModelSerializer):
    entries = serializers.IntegerField(source="entries.count", read_only=True)

    class Meta:
        model = TimetableVersion
        fields = ["id", "label", "source", "term_start", "term_end", "published_at", "is_current", "displaced_bookings", "entries"]


class EntrySerializer(serializers.ModelSerializer):
    resource_code = serializers.CharField(source="resource.code", read_only=True)
    resource_name = serializers.CharField(source="resource.name", read_only=True)

    class Meta:
        model = TimetableEntry
        fields = ["id", "resource", "resource_code", "resource_name", "weekday", "start_time", "end_time",
                  "course_code", "course_name", "section", "faculty_name"]


@api_view(["POST"])
@permission_classes([AllowAny])
def publish(request):
    """
    Webhook for P13 (timetable system) — or a facility manager uploading JSON by hand.
    Machine callers authenticate with header `X-Timetable-Token: <TIMETABLE_WEBHOOK_TOKEN>`.
    """
    token = request.headers.get("X-Timetable-Token", "")
    machine = bool(settings.TIMETABLE_WEBHOOK_TOKEN) and hmac.compare_digest(token, settings.TIMETABLE_WEBHOOK_TOKEN)
    if not machine and not (request.user.is_authenticated and IsPolicyAdmin().has_permission(request, None)):
        return Response({"error": "forbidden", "message": "Facility manager or P13 token required."}, status=403)
    version, changed = services.publish(request.data, source="p13-webhook" if machine else f"upload:{request.user}")
    return Response({"changed": changed, "version": VersionSerializer(version).data}, status=201 if changed else 200)


@api_view(["GET"])
def current(request):
    v = TimetableVersion.objects.filter(is_current=True).first()
    if not v:
        return Response({"version": None, "entries": []})
    entries = v.entries.select_related("resource")
    if r := request.query_params.get("resource"):
        entries = entries.filter(resource_id=r)
    return Response({"version": VersionSerializer(v).data, "entries": EntrySerializer(entries, many=True).data})


@api_view(["GET"])
def versions(request):
    return Response(VersionSerializer(TimetableVersion.objects.all()[:20], many=True).data)
