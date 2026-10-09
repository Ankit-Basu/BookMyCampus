from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.db import models


class ApprovalWorkflow(models.Model):
    """
    A chain of approval steps, selected by resource type + requester role. Edited from the admin
    dashboard at runtime — no deployment needed to change who approves what.
    """

    name = models.CharField(max_length=120)
    resource_type = models.ForeignKey("catalogue.ResourceType", on_delete=models.CASCADE, related_name="workflows")
    # Requester roles this workflow applies to. Empty = every role.
    requester_roles = ArrayField(models.CharField(max_length=24), default=list, blank=True)
    is_active = models.BooleanField(default=True)
    # Higher wins when several workflows match.
    priority = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["resource_type__name", "-priority"]

    def __str__(self):
        return self.name


class ApprovalStep(models.Model):
    class ApproverRole(models.TextChoices):
        CUSTODIAN = "custodian", "Resource custodian"
        DEPT_HEAD = "dept_head", "Department head"
        FACILITY_MANAGER = "facility_manager", "Facility manager"

    workflow = models.ForeignKey(ApprovalWorkflow, on_delete=models.CASCADE, related_name="steps")
    order = models.PositiveSmallIntegerField()
    name = models.CharField(max_length=80)
    approver_role = models.CharField(max_length=24, choices=ApproverRole.choices)
    sla_hours = models.PositiveSmallIntegerField(default=24)

    class Meta:
        ordering = ["order"]
        unique_together = [("workflow", "order")]


class Approval(models.Model):
    class Status(models.TextChoices):
        WAITING = "waiting", "Waiting on earlier step"
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    booking = models.ForeignKey("bookings.Booking", on_delete=models.CASCADE, related_name="approvals")
    order = models.PositiveSmallIntegerField()
    step_name = models.CharField(max_length=80)
    approver_role = models.CharField(max_length=24)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.WAITING)
    decided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    decided_at = models.DateTimeField(null=True, blank=True)
    activated_at = models.DateTimeField(null=True, blank=True)
    comment = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["booking", "order"]
