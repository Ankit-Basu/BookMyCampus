from django.db import transaction
from rest_framework import serializers, viewsets
from rest_framework.decorators import api_view
from rest_framework.response import Response

from apps.accounts.permissions import ReadOnlyOrPolicyAdmin
from apps.bookings.serializers import BookingSerializer

from .models import ApprovalStep, ApprovalWorkflow
from .services import queue_for


class StepSerializer(serializers.ModelSerializer):
    class Meta:
        model = ApprovalStep
        fields = ["id", "order", "name", "approver_role", "sla_hours"]
        read_only_fields = ["id", "order"]  # assigned from list position on save


class WorkflowSerializer(serializers.ModelSerializer):
    steps = StepSerializer(many=True)
    resource_type_name = serializers.CharField(source="resource_type.name", read_only=True)

    class Meta:
        model = ApprovalWorkflow
        fields = ["id", "name", "resource_type", "resource_type_name", "requester_roles", "is_active", "priority", "steps"]

    def _write_steps(self, wf, steps):
        wf.steps.all().delete()
        for i, s in enumerate(steps, start=1):
            s.pop("order", None)
            ApprovalStep.objects.create(workflow=wf, order=i, **s)

    @transaction.atomic
    def create(self, validated):
        steps = validated.pop("steps", [])
        wf = ApprovalWorkflow.objects.create(**validated)
        self._write_steps(wf, steps)
        return wf

    @transaction.atomic
    def update(self, instance, validated):
        steps = validated.pop("steps", None)
        instance = super().update(instance, validated)
        if steps is not None:
            self._write_steps(instance, steps)
        return instance


class WorkflowViewSet(viewsets.ModelViewSet):
    """Workflow builder — changes take effect on the next booking, no deployment."""

    queryset = ApprovalWorkflow.objects.select_related("resource_type").prefetch_related("steps")
    serializer_class = WorkflowSerializer
    permission_classes = [ReadOnlyOrPolicyAdmin]


@api_view(["GET"])
def approval_queue(request):
    approvals = list(queue_for(request.user).order_by("booking__period"))
    out = []
    for a in approvals:
        data = BookingSerializer(a.booking).data
        data["current_step"] = {"id": a.id, "name": a.step_name, "role": a.approver_role, "activated_at": a.activated_at}
        data["requester_department"] = a.booking.user.department.code if a.booking.user.department else None
        data["requester_role"] = a.booking.user.get_role_display()
        out.append(data)
    return Response(out)
