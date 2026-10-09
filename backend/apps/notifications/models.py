from django.conf import settings
from django.db import models


class Notification(models.Model):
    class Kind(models.TextChoices):
        CONFIRMED = "confirmed", "Booking confirmed"
        APPROVAL_REQUIRED = "approval_required", "Approval required"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        REMINDER = "reminder", "Reminder"
        CHECKIN_REQUIRED = "checkin_required", "Check-in required"
        RELEASED = "released", "Auto-released"
        MAINTENANCE = "maintenance", "Maintenance scheduled"
        UNAVAILABLE = "unavailable", "Resource unavailable"
        RESTRICTED = "restricted", "Booking restricted"
        STOCK = "stock", "Low stock"
        INFO = "info", "Info"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.INFO)
    title = models.CharField(max_length=160)
    body = models.TextField(blank=True)
    link = models.CharField(max_length=200, blank=True)
    booking = models.ForeignKey("bookings.Booking", null=True, blank=True, on_delete=models.CASCADE)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
