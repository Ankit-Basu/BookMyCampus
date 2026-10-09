from django.shortcuts import get_object_or_404
from django.utils.dateparse import parse_datetime
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsManager
from apps.catalogue.models import Resource
from apps.common.fields import RangeBoundsMixin

from . import services
from .models import MaintenanceWindow


class MaintenanceSerializer(RangeBoundsMixin, serializers.ModelSerializer):
    resource_name = serializers.CharField(source="resource.name", read_only=True)
    resource_code = serializers.CharField(source="resource.code", read_only=True)
    reported_by_name = serializers.CharField(source="reported_by.get_full_name", read_only=True, default=None)

    class Meta:
        model = MaintenanceWindow
        fields = [
            "id", "resource", "resource_name", "resource_code", "kind", "title", "notes", "start", "end", "status",
            "reported_by_name", "created_at", "resolved_at", "displaced_bookings",
        ]


class MaintenanceViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    GET  /maintenance/?resource=&from=&to=&status=
    POST /maintenance/                  schedule {resource, start, end, title, notes}
    POST /maintenance/report            breakdown {resource, title, notes, hours} — anyone can report
    POST /maintenance/:id/resolve | cancel
    """

    serializer_class = MaintenanceSerializer

    def get_permissions(self):
        if self.action in ("report", "list", "retrieve"):
            return [IsAuthenticated()]
        return [IsManager()]

    def get_queryset(self):
        qs = MaintenanceWindow.objects.select_related("resource", "reported_by")
        p = self.request.query_params
        if r := p.get("resource"):
            qs = qs.filter(resource_id=r)
        if s := p.get("status"):
            qs = qs.filter(status__in=s.split(","))
        f, t = parse_datetime(p.get("from", "") or ""), parse_datetime(p.get("to", "") or "")
        if f and t:
            qs = qs.filter(period__overlap=(f, t))
        return qs

    def create(self, request):
        r = get_object_or_404(Resource, pk=request.data.get("resource"))
        s, e = parse_datetime(request.data.get("start", "")), parse_datetime(request.data.get("end", ""))
        if not (s and e):
            return Response({"error": "invalid_period", "message": "start and end are required"}, status=400)
        w = services.schedule(r, s, e, title=request.data.get("title") or "Scheduled maintenance",
                              notes=request.data.get("notes", ""), by=request.user)
        return Response(MaintenanceSerializer(w).data, status=201)

    @action(detail=False, methods=["post"])
    def report(self, request):
        r = get_object_or_404(Resource, pk=request.data.get("resource"))
        w = services.report_breakdown(
            r, request.user, request.data.get("title") or "Reported fault", request.data.get("notes", ""),
            int(request.data.get("hours", 24)),
        )
        return Response(MaintenanceSerializer(w).data, status=201)

    @action(detail=True, methods=["post"])
    def resolve(self, request, pk=None):
        return Response(MaintenanceSerializer(services.resolve(self.get_object())).data)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        return Response(MaintenanceSerializer(services.cancel(self.get_object())).data)
