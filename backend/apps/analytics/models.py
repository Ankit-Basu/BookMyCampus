from django.db import models


class UtilisationSnapshot(models.Model):
    """Daily roll-up per resource, written by the nightly task. Reports read from here for history."""

    resource = models.ForeignKey("catalogue.Resource", on_delete=models.CASCADE, related_name="snapshots")
    date = models.DateField()
    available_minutes = models.PositiveIntegerField(default=0)
    booked_minutes = models.PositiveIntegerField(default=0)
    used_minutes = models.PositiveIntegerField(default=0)
    timetable_minutes = models.PositiveIntegerField(default=0)
    maintenance_minutes = models.PositiveIntegerField(default=0)
    bookings = models.PositiveIntegerField(default=0)
    no_shows = models.PositiveIntegerField(default=0)

    class Meta:
        unique_together = [("resource", "date")]
        ordering = ["-date"]
