"""The demo's student lab requests went to a lab custodian, whom the demo personas cannot sign in as."""
from django.db import migrations


def forwards(apps, schema_editor):
    Step = apps.get_model("approvals", "ApprovalStep")
    Approval = apps.get_model("approvals", "Approval")
    Step.objects.filter(workflow__name="Student lab access", approver_role="custodian").update(
        approver_role="dept_head", name="HOD approval"
    )
    Approval.objects.filter(status__in=["pending", "waiting"], approver_role="custodian", step_name="Lab custodian").update(
        approver_role="dept_head", step_name="HOD approval"
    )


class Migration(migrations.Migration):
    dependencies = [("approvals", "0001_initial")]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
