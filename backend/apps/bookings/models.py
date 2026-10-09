import secrets
import uuid

from django.conf import settings
from django.contrib.postgres.constraints import ExclusionConstraint
from django.contrib.postgres.fields import ArrayField, DateTimeRangeField, RangeOperators
from django.db import models


def make_reference():
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
    return "BMC-" + "".join(secrets.choice(alphabet) for _ in range(6))


class RecurrenceRule(models.Model):
    class Freq(models.TextChoices):
        DAILY = "daily", "Daily"
        WEEKLY = "weekly", "Weekly"

    class ConflictPolicy(models.TextChoices):
        SKIP = "skip", "Book the free occurrences, skip conflicts"
        ABORT = "abort", "All or nothing"

    freq = models.CharField(max_length=8, choices=Freq.choices, default=Freq.WEEKLY)
    interval = models.PositiveSmallIntegerField(default=1)
    weekdays = ArrayField(models.PositiveSmallIntegerField(), default=list, blank=True)
    until = models.DateField(null=True, blank=True)
    count = models.PositiveSmallIntegerField(null=True, blank=True)
    conflict_policy = models.CharField(max_length=8, choices=ConflictPolicy.choices, default=ConflictPolicy.SKIP)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="recurrences")
    created_at = models.DateTimeField(auto_now_add=True)
    requested_occurrences = models.PositiveSmallIntegerField(default=0)
    skipped = models.JSONField(default=list, blank=True)


class Booking(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Awaiting approval"
        CONFIRMED = "confirmed", "Confirmed"
        CHECKED_IN = "checked_in", "Checked in"
        COMPLETED = "completed", "Completed"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"
        RELEASED = "released", "Auto-released (no-show)"
        DISPLACED = "displaced", "Displaced by timetable / maintenance"

    # Statuses that hold the slot. Everything else frees it.
    ACTIVE = (Status.PENDING, Status.CONFIRMED, Status.CHECKED_IN)

    reference = models.CharField(max_length=12, unique=True, default=make_reference, editable=False)
    resource = models.ForeignKey("catalogue.Resource", on_delete=models.PROTECT, related_name="bookings")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="bookings")
    title = models.CharField(max_length=160)
    purpose = models.TextField(blank=True)
    on_behalf_of = models.CharField(max_length=80, blank=True, help_text="Class/section this booking is for")
    attendees = models.PositiveIntegerField(default=1)
    period = DateTimeRangeField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.CONFIRMED, db_index=True)
    recurrence = models.ForeignKey(RecurrenceRule, null=True, blank=True, on_delete=models.SET_NULL, related_name="bookings")
    occurrence_index = models.PositiveSmallIntegerField(null=True, blank=True)
    qr_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status_note = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    reminder_sent = models.BooleanField(default=False)

    class Meta:
        ordering = ["period"]
        indexes = [models.Index(fields=["resource", "status"])]
        constraints = [
            # THE core guarantee: two live bookings for the same resource can never overlap.
            # PostgreSQL enforces this with a GiST index; concurrent inserts serialise on it,
            # so it holds no matter how many requests race for the slot.
            ExclusionConstraint(
                name="booking_no_overlap",
                expressions=[("resource", RangeOperators.EQUAL), ("period", RangeOperators.OVERLAPS)],
                condition=models.Q(status__in=["pending", "confirmed", "checked_in"]),
            ),
        ]

    def __str__(self):
        return f"{self.reference} {self.resource.code}"

    @property
    def start(self):
        return self.period.lower

    @property
    def end(self):
        return self.period.upper

    @property
    def is_active(self):
        return self.status in self.ACTIVE


class BookingSlot(models.Model):
    """
    The unified occupancy ledger. Every thing that occupies a resource — a booking, a timetabled
    class, a maintenance window — claims a row here. One exclusion constraint over this table means
    a booking physically cannot be stored over a lecture or a repair, not just "is not offered".
    Rows exist only while the occupancy holds; releasing a booking deletes its slot.
    """

    class Kind(models.TextChoices):
        BOOKING = "booking", "Booking"
        TIMETABLE = "timetable", "Timetabled class"
        MAINTENANCE = "maintenance", "Maintenance"

    resource = models.ForeignKey("catalogue.Resource", on_delete=models.CASCADE, related_name="slots")
    period = DateTimeRangeField()
    kind = models.CharField(max_length=12, choices=Kind.choices)
    label = models.CharField(max_length=160, blank=True)
    booking = models.OneToOneField(Booking, null=True, blank=True, on_delete=models.CASCADE, related_name="slot")
    timetable_entry = models.ForeignKey(
        "timetable.TimetableEntry", null=True, blank=True, on_delete=models.CASCADE, related_name="slots"
    )
    maintenance = models.ForeignKey(
        "maintenance.MaintenanceWindow", null=True, blank=True, on_delete=models.CASCADE, related_name="slots"
    )

    class Meta:
        constraints = [
            ExclusionConstraint(
                name="slot_no_overlap",
                expressions=[("resource", RangeOperators.EQUAL), ("period", RangeOperators.OVERLAPS)],
            ),
        ]


class BookingAttempt(models.Model):
    """Every booking request, successful or not — the 'demand' side of demand-vs-supply."""

    class Outcome(models.TextChoices):
        BOOKED = "booked", "Booked"
        CONFLICT = "conflict", "Slot taken"
        RULE = "rule", "Rule violation"

    resource = models.ForeignKey("catalogue.Resource", on_delete=models.CASCADE, related_name="attempts")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    period = DateTimeRangeField()
    outcome = models.CharField(max_length=10, choices=Outcome.choices)
    reason = models.CharField(max_length=240, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)


class CheckIn(models.Model):
    class Method(models.TextChoices):
        RESOURCE_QR = "resource_qr", "Scanned resource QR"
        BOOKING_QR = "booking_qr", "Custodian scanned booking pass"
        MANUAL = "manual", "Manual"

    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name="checkin")
    checked_in_at = models.DateTimeField(auto_now_add=True)
    method = models.CharField(max_length=12, choices=Method.choices)
    verified_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    checked_out_at = models.DateTimeField(null=True, blank=True)
    condition_note = models.CharField(max_length=240, blank=True)


class NoShow(models.Model):
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name="noshow")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="noshows")
    resource = models.ForeignKey("catalogue.Resource", on_delete=models.CASCADE, related_name="noshows")
    recorded_at = models.DateTimeField(auto_now_add=True)
    waived = models.BooleanField(default=False)
    waived_reason = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["-recorded_at"]
