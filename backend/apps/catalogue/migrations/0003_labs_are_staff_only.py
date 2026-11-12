"""Laboratories are booked by faculty and staff only. Upcoming student lab bookings in the demo data are withdrawn."""
from django.db import migrations
from django.utils import timezone

STAFF_ROLES = ["faculty", "staff", "custodian", "dept_head", "facility_manager", "admin"]
NOTE = "Withdrawn: laboratories are now booked by faculty and staff only."


def forwards(apps, schema_editor):
    ResourceType = apps.get_model("catalogue", "ResourceType")
    Workflow = apps.get_model("approvals", "ApprovalWorkflow")
    Approval = apps.get_model("approvals", "Approval")
    Booking = apps.get_model("bookings", "Booking")
    BookingSlot = apps.get_model("bookings", "BookingSlot")

    labs = ResourceType.objects.filter(name="Laboratory")
    if not labs.exists():
        return
    labs.update(allowed_roles=STAFF_ROLES, description="Teaching and research labs. Faculty and staff book these.")
    Workflow.objects.filter(name="Student lab access").update(is_active=False)

    upcoming = Booking.objects.filter(
        resource__type__name="Laboratory",
        user__role="student",
        status__in=["pending", "confirmed"],
        period__startswith__gt=timezone.now(),
    )
    ids = list(upcoming.values_list("id", flat=True))
    BookingSlot.objects.filter(booking_id__in=ids).delete()
    Approval.objects.filter(booking_id__in=ids, status__in=["waiting", "pending"]).update(status="cancelled")
    Booking.objects.filter(id__in=ids).update(status="cancelled", status_note=NOTE, decided_at=timezone.now())


class Migration(migrations.Migration):
    dependencies = [
        ("catalogue", "0002_resource_saved_by"),
        ("approvals", "0002_hod_approves_student_lab_requests"),
        ("bookings", "0002_slotwatch"),
    ]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
