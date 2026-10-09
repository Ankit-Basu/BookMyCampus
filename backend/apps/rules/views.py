from django.utils.dateparse import parse_datetime
from rest_framework import serializers, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.permissions import IsPolicyAdmin, ReadOnlyOrManager, ReadOnlyOrPolicyAdmin
from apps.bookings.services import tsrange
from apps.common.fields import RangeBoundsMixin

from .models import AvailabilityRule, Blackout, Policy, Quota


class AvailabilityRuleSerializer(serializers.ModelSerializer):
    target = serializers.SerializerMethodField()

    class Meta:
        model = AvailabilityRule
        fields = [
            "id", "resource_type", "resource", "target", "name", "weekdays", "open_time", "close_time",
            "min_duration_minutes", "max_duration_minutes", "min_lead_minutes", "max_advance_days", "slot_minutes",
        ]

    def get_target(self, obj):
        return str(obj.resource or obj.resource_type)

    def validate(self, attrs):
        if not attrs.get("resource_type") and not attrs.get("resource") and not self.instance:
            raise serializers.ValidationError("Choose a resource type or a single resource.")
        return attrs


class BlackoutSerializer(RangeBoundsMixin, serializers.ModelSerializer):
    start_at = serializers.DateTimeField(write_only=True)
    end_at = serializers.DateTimeField(write_only=True)
    scope = serializers.SerializerMethodField()

    class Meta:
        model = Blackout
        fields = ["id", "title", "start", "end", "start_at", "end_at", "resource_type", "resource", "scope"]

    def get_scope(self, obj):
        return str(obj.resource or obj.resource_type or "Entire campus")

    def _period(self, attrs):
        s, e = attrs.pop("start_at", None), attrs.pop("end_at", None)
        if s and e:
            if e <= s:
                raise serializers.ValidationError("End must be after start.")
            attrs["period"] = tsrange(s, e)
        return attrs

    def create(self, validated):
        return super().create(self._period(validated))

    def update(self, instance, validated):
        return super().update(instance, self._period(validated))


class QuotaSerializer(serializers.ModelSerializer):
    label = serializers.CharField(source="__str__", read_only=True)

    class Meta:
        model = Quota
        fields = [
            "id", "label", "department", "role", "resource_type", "department_hours_per_week",
            "user_hours_per_week", "max_active_bookings",
        ]


class PolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = Policy
        exclude = ["id"]


class AvailabilityRuleViewSet(viewsets.ModelViewSet):
    queryset = AvailabilityRule.objects.select_related("resource", "resource_type")
    serializer_class = AvailabilityRuleSerializer
    permission_classes = [ReadOnlyOrManager]
    filterset_fields = ["resource", "resource_type"]


class BlackoutViewSet(viewsets.ModelViewSet):
    queryset = Blackout.objects.select_related("resource", "resource_type")
    serializer_class = BlackoutSerializer
    permission_classes = [ReadOnlyOrManager]

    def get_queryset(self):
        qs = super().get_queryset()
        if upcoming := self.request.query_params.get("after"):
            dt = parse_datetime(upcoming)
            if dt:
                qs = qs.filter(period__endswith__gte=dt)
        return qs


class QuotaViewSet(viewsets.ModelViewSet):
    queryset = Quota.objects.select_related("department", "resource_type")
    serializer_class = QuotaSerializer
    permission_classes = [ReadOnlyOrPolicyAdmin]


@api_view(["GET", "PUT", "PATCH"])
@permission_classes([IsAuthenticated])
def policy_view(request):
    policy = Policy.get()
    if request.method == "GET":
        return Response(PolicySerializer(policy).data)
    if not IsPolicyAdmin().has_permission(request, None):
        return Response({"error": "forbidden", "message": "Only facility managers can change policy."}, status=403)
    s = PolicySerializer(policy, data=request.data, partial=True)
    s.is_valid(raise_exception=True)
    s.save()
    return Response(s.data)
