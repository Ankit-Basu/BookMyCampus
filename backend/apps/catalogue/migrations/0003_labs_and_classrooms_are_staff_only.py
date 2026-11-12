"""Labs and classrooms are booked by faculty and staff only: labs for practicals, classrooms for classes and make-up classes.
Upcoming student bookings of either in the demo data are withdrawn."""
from django.db import migrations
from django.utils import timezone

STAFF_ROLES = ["faculty", "staff", "custodian", "dept_head", "facility_manager", "admin"]
NOTE = "Withdrawn: labs and classrooms are now booked by faculty and staff only."
DESCRIPTIONS = {
    "Laboratory": "Teaching and research labs. Faculty and staff book these for practicals.",
    "Classroom": "Lecture rooms with projection. Faculty book these for classes and make-up classes.",
}


def forwards(apps, schema_editor):
    ResourceType = apps.get_model("catalogue", "ResourceType")
    Workflow = apps.get_model("approvals", "ApprovalWorkflow")
    Approval = apps.get_model("approvals", "Approval")
    Booking = apps.get_model("bookings", "Booking")
    BookingSlot = apps.get_model("bookings", "BookingSlot")

    for name, description in DESCRIPTIONS.items():
        ResourceType.objects.filter(name=name).update(allowed_roles=STAFF_ROLES, description=description)
    Workflow.objects.filter(name__in=["Student lab access", "Students in classrooms"]).update(is_active=False)

    upcoming = Booking.objects.filter(
        resource__type__name__in=list(DESCRIPTIONS),
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
