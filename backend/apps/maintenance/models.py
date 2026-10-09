from django.conf import settings
from django.contrib.postgres.fields import DateTimeRangeField
from django.db import models


class MaintenanceWindow(models.Model):
    class Kind(models.TextChoices):
        SCHEDULED = "scheduled", "Scheduled maintenance"
        BREAKDOWN = "breakdown", "Breakdown"

    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        IN_PROGRESS = "in_progress", "In progress"
        DONE = "done", "Done"
        CANCELLED = "cancelled", "Cancelled"

    resource = models.ForeignKey("catalogue.Resource", on_delete=models.CASCADE, related_name="maintenance")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.SCHEDULED)
    title = models.CharField(max_length=160)
    notes = models.TextField(blank=True)
    period = DateTimeRangeField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLANNED)
    reported_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    displaced_bookings = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-period"]

    def __str__(self):
        return f"{self.resource.code}: {self.title}"
