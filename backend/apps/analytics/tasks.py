from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.catalogue.models import Resource

from .models import UtilisationSnapshot
from .services import resource_utilisation


@shared_task
def nightly_snapshot(days_back=1):
    """Persist yesterday's per-resource utilisation so history survives catalogue/rule edits."""
    today = timezone.localdate()
    written = 0
    for offset in range(1, days_back + 1):
        d = today - timedelta(days=offset)
        for row in resource_utilisation(d, d + timedelta(days=1), Resource.objects.select_related("type", "department")):
            UtilisationSnapshot.objects.update_or_create(
                resource_id=row["resource_id"], date=d,
                defaults={
                    "available_minutes": int(row["supply_hours"] * 60), "booked_minutes": int(row["booked_hours"] * 60),
                    "used_minutes": int(row["used_hours"] * 60), "timetable_minutes": int(row["teaching_hours"] * 60),
                    "maintenance_minutes": int(row["maintenance_hours"] * 60), "bookings": row["bookings"],
                    "no_shows": row["no_shows"],
                },
            )
            written += 1
    return written
