from django.db import models


class TimetableVersion(models.Model):
    """
    One publication of the academic timetable (from P13). Only one version is current; publishing
    a new one atomically replaces every timetable slot in the occupancy ledger.
    """

    label = models.CharField(max_length=80)
    source = models.CharField(max_length=200, default="manual")
    term_start = models.DateField()
    term_end = models.DateField()
    published_at = models.DateTimeField(auto_now_add=True)
    is_current = models.BooleanField(default=False)
    checksum = models.CharField(max_length=64, blank=True)
    displaced_bookings = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-published_at"]
        constraints = [
            models.UniqueConstraint(fields=["is_current"], condition=models.Q(is_current=True), name="one_current_timetable")
        ]

    def __str__(self):
        return self.label


class TimetableEntry(models.Model):
    version = models.ForeignKey(TimetableVersion, on_delete=models.CASCADE, related_name="entries")
    resource = models.ForeignKey("catalogue.Resource", on_delete=models.CASCADE, related_name="timetable_entries")
    weekday = models.PositiveSmallIntegerField(help_text="Monday=0")
    start_time = models.TimeField()
    end_time = models.TimeField()
    course_code = models.CharField(max_length=20)
    course_name = models.CharField(max_length=160, blank=True)
    section = models.CharField(max_length=20, blank=True)
    faculty_name = models.CharField(max_length=120, blank=True)

    class Meta:
        ordering = ["weekday", "start_time"]

    def __str__(self):
        return f"{self.course_code} {self.section} @ {self.resource.code}"
