from django.contrib.postgres.fields import ArrayField, DateTimeRangeField
from django.db import models


class AvailabilityRule(models.Model):
    """
    Opening hours + booking limits. A rule targets either a single resource or a whole
    resource type. Resource-level rules fully override type-level rules for that resource.
    Several rules may coexist (e.g. Mon–Fri 08:00–20:00 and Sat 09:00–13:00).
    """

    resource_type = models.ForeignKey(
        "catalogue.ResourceType", null=True, blank=True, on_delete=models.CASCADE, related_name="rules"
    )
    resource = models.ForeignKey("catalogue.Resource", null=True, blank=True, on_delete=models.CASCADE, related_name="rules")
    name = models.CharField(max_length=80, default="Standard hours")
    # ISO weekdays, Monday=0 … Sunday=6
    weekdays = ArrayField(models.PositiveSmallIntegerField(), default=list)
    open_time = models.TimeField()
    close_time = models.TimeField()
    min_duration_minutes = models.PositiveIntegerField(default=30)
    max_duration_minutes = models.PositiveIntegerField(default=180)
    min_lead_minutes = models.PositiveIntegerField(default=0, help_text="How far ahead a booking must be made")
    max_advance_days = models.PositiveIntegerField(default=30, help_text="Booking window — how far into the future")
    slot_minutes = models.PositiveIntegerField(default=30, help_text="Granularity of bookable slots")

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(resource_type__isnull=False) | models.Q(resource__isnull=False),
                name="rule_has_target",
            ),
            models.CheckConstraint(condition=models.Q(open_time__lt=models.F("close_time")), name="rule_open_before_close"),
        ]

    def __str__(self):
        target = self.resource or self.resource_type
        return f"{target}: {self.name}"


class Blackout(models.Model):
    """A period in which nothing in scope can be booked (exams, holidays, events)."""

    title = models.CharField(max_length=120)
    period = DateTimeRangeField()
    # Scope: everything (both null), a type, or a single resource.
    resource_type = models.ForeignKey(
        "catalogue.ResourceType", null=True, blank=True, on_delete=models.CASCADE, related_name="blackouts"
    )
    resource = models.ForeignKey(
        "catalogue.Resource", null=True, blank=True, on_delete=models.CASCADE, related_name="blackouts"
    )

    class Meta:
        ordering = ["period"]

    def __str__(self):
        return self.title


class Quota(models.Model):
    """
    Departmental / role quota per ISO week. Matches by department and/or role and optionally
    a resource type; the most specific matching quotas all apply.
    """

    department = models.ForeignKey(
        "accounts.Department", null=True, blank=True, on_delete=models.CASCADE, related_name="quotas"
    )
    role = models.CharField(max_length=24, blank=True)
    resource_type = models.ForeignKey(
        "catalogue.ResourceType", null=True, blank=True, on_delete=models.CASCADE, related_name="quotas"
    )
    # Department-wide hours per week (sum of all members) — 0 = unlimited
    department_hours_per_week = models.PositiveIntegerField(default=0)
    # Per-user hours per week — 0 = unlimited
    user_hours_per_week = models.PositiveIntegerField(default=0)
    # Per-user simultaneous upcoming bookings — 0 = unlimited
    max_active_bookings = models.PositiveIntegerField(default=0)

    def __str__(self):
        bits = [str(self.department or "All depts"), self.role or "all roles", str(self.resource_type or "all types")]
        return " / ".join(bits)


class Policy(models.Model):
    """Singleton for campus-wide behaviour, editable by the facility manager at runtime."""

    checkin_open_minutes = models.PositiveIntegerField(default=15, help_text="Check-in opens this long before start")
    grace_minutes = models.PositiveIntegerField(default=15, help_text="Auto-release if not checked in by start + grace")
    reminder_minutes = models.PositiveIntegerField(default=30)
    noshow_window_days = models.PositiveIntegerField(default=30)
    # Progressive restriction ladder: (strikes → days restricted)
    strike_warn = models.PositiveIntegerField(default=2)
    strike_level1 = models.PositiveIntegerField(default=3)
    restrict_days_level1 = models.PositiveIntegerField(default=7)
    strike_level2 = models.PositiveIntegerField(default=5)
    restrict_days_level2 = models.PositiveIntegerField(default=30)
    # Stamped by every sweeper run (thread, management command or Celery) — powers the health strip.
    last_sweep_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name_plural = "policy"

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
