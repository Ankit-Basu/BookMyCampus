"""
Tests for apps.approvals — multi-tier approval workflows.

Covers:
  • ApprovalWorkflow / ApprovalStep model creation
  • resolve_workflow() — priority-based matching + role filtering
  • attach_workflow() — creates Approval rows, activates the first step
  • decide() — approve chain, reject chain, forbidden user, series approve
  • queue_for() — returns only approvals the user is authorised to decide
  • Workflow CRUD via /api/workflows (WorkflowViewSet)
  • /api/approvals/queue endpoint
"""

from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from psycopg.types.range import Range
from rest_framework.test import APIClient

from apps.accounts.models import Department, Role, User
from apps.bookings.models import Booking, BookingSlot
from apps.catalogue.models import Location, Resource, ResourceType

from .models import Approval, ApprovalStep, ApprovalWorkflow
from .services import (
    approvers_for,
    attach_workflow,
    can_decide,
    decide,
    queue_for,
    resolve_workflow,
)


def _ts(offset_hours=0):
    """Return a timezone-aware datetime offset from 'now'."""
    return timezone.now() + timedelta(hours=offset_hours)


def _make_booking(resource, user, start_offset=1, duration=1, status="pending"):
    """Create a Booking + its occupancy BookingSlot."""
    s = _ts(start_offset)
    e = s + timedelta(hours=duration)
    b = Booking.objects.create(
        resource=resource,
        user=user,
        title="Test booking",
        period=Range(s, e, bounds="[)"),
        status=status,
        attendees=1,
    )
    BookingSlot.objects.create(
        resource=resource,
        period=Range(s, e, bounds="[)"),
        kind=BookingSlot.Kind.BOOKING,
        booking=b,
    )
    return b


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class ApprovalModelTests(TestCase):
    """Basic model creation & string representation."""

    @classmethod
    def setUpTestData(cls):
        cls.rt = ResourceType.objects.create(name="Lecture Hall", slug="lecture-hall")
        cls.wf = ApprovalWorkflow.objects.create(name="Std LH", resource_type=cls.rt, priority=10)
        ApprovalStep.objects.create(workflow=cls.wf, order=1, name="Custodian OK", approver_role="custodian")
        ApprovalStep.objects.create(workflow=cls.wf, order=2, name="Dept Head OK", approver_role="dept_head")

    def test_workflow_str(self):
        self.assertEqual(str(self.wf), "Std LH")

    def test_steps_ordered(self):
        steps = list(self.wf.steps.all())
        self.assertEqual(len(steps), 2)
        self.assertEqual(steps[0].order, 1)
        self.assertEqual(steps[1].order, 2)

    def test_unique_order_per_workflow(self):
        """Two steps with the same order in the same workflow should violate unique_together."""
        from django.db import IntegrityError

        with self.assertRaises(IntegrityError):
            ApprovalStep.objects.create(workflow=self.wf, order=1, name="Dup", approver_role="custodian")


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class ResolveWorkflowTests(TestCase):
    """Test resolve_workflow() — picks highest-priority active workflow matching requester role."""

    @classmethod
    def setUpTestData(cls):
        cls.rt = ResourceType.objects.create(name="Lab-R", slug="lab-r")
        cls.loc = Location.objects.create(building="B1")
        cls.resource = Resource.objects.create(type=cls.rt, code="LAB-R-01", name="Lab R1", location=cls.loc)
        cls.student = User.objects.create_user("stu_r", password="p", role=Role.STUDENT)
        cls.faculty = User.objects.create_user("fac_r", password="p", role=Role.FACULTY)

        # Low-priority workflow for everyone
        cls.wf_general = ApprovalWorkflow.objects.create(name="General", resource_type=cls.rt, priority=0)
        ApprovalStep.objects.create(workflow=cls.wf_general, order=1, name="FM Check", approver_role="facility_manager")

        # High-priority workflow restricted to students
        cls.wf_student = ApprovalWorkflow.objects.create(
            name="Student Extra", resource_type=cls.rt, priority=10, requester_roles=["student"]
        )
        ApprovalStep.objects.create(workflow=cls.wf_student, order=1, name="Custodian", approver_role="custodian")
        ApprovalStep.objects.create(workflow=cls.wf_student, order=2, name="Dept Head", approver_role="dept_head")

    def test_student_gets_higher_priority_workflow(self):
        wf = resolve_workflow(self.resource, self.student)
        self.assertEqual(wf, self.wf_student)

    def test_faculty_gets_general_workflow(self):
        wf = resolve_workflow(self.resource, self.faculty)
        self.assertEqual(wf, self.wf_general)

    def test_no_workflow_when_inactive(self):
        self.wf_general.is_active = False
        self.wf_general.save()
        self.wf_student.is_active = False
        self.wf_student.save()
        wf = resolve_workflow(self.resource, self.student)
        self.assertIsNone(wf)
        # Restore
        self.wf_general.is_active = True
        self.wf_general.save()
        self.wf_student.is_active = True
        self.wf_student.save()

    def test_workflow_without_steps_returns_none(self):
        """An empty workflow (no steps) at highest priority makes resolve_workflow return None
        because it picks the top match and checks steps — it does NOT fall through."""
        empty_wf = ApprovalWorkflow.objects.create(name="Empty WF", resource_type=self.rt, priority=100)
        wf = resolve_workflow(self.resource, self.student)
        self.assertIsNone(wf)
        empty_wf.delete()


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class AttachAndDecideTests(TestCase):
    """
    Test the full approval lifecycle:
    attach_workflow → Approval rows created → decide approve/reject → booking status updated.
    """

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(code="CS", name="Computer Science")
        cls.rt = ResourceType.objects.create(name="Seminar-A", slug="seminar-a")
        cls.loc = Location.objects.create(building="B2")
        cls.resource = Resource.objects.create(
            type=cls.rt, code="SEM-A-01", name="Seminar A1", location=cls.loc, department=cls.dept
        )

        # Users
        cls.requester = User.objects.create_user("req_a", password="p", role=Role.STUDENT, department=cls.dept)
        cls.custodian = User.objects.create_user("cust_a", password="p", role=Role.CUSTODIAN, department=cls.dept)
        cls.resource.custodians.add(cls.custodian)
        cls.dept_head = User.objects.create_user("dh_a", password="p", role=Role.DEPT_HEAD, department=cls.dept)
        cls.admin = User.objects.create_user("adm_a", password="p", role=Role.ADMIN, is_superuser=True)

        # 2-step workflow
        cls.wf = ApprovalWorkflow.objects.create(name="2-step SEM", resource_type=cls.rt, priority=5)
        ApprovalStep.objects.create(workflow=cls.wf, order=1, name="Custodian OK", approver_role="custodian")
        ApprovalStep.objects.create(workflow=cls.wf, order=2, name="Dept Head OK", approver_role="dept_head")

    def _fresh_booking(self, offset=1):
        return _make_booking(self.resource, self.requester, start_offset=offset, status="pending")

    def test_attach_creates_approvals(self):
        b = self._fresh_booking(offset=100)
        attach_workflow(b, self.wf)

        approvals = list(b.approvals.order_by("order"))
        self.assertEqual(len(approvals), 2)
        # First step should be activated (PENDING), second still WAITING
        self.assertEqual(approvals[0].status, Approval.Status.PENDING)
        self.assertIsNotNone(approvals[0].activated_at)
        self.assertEqual(approvals[1].status, Approval.Status.WAITING)
        self.assertIsNone(approvals[1].activated_at)

    def test_approve_chain_confirms_booking(self):
        b = self._fresh_booking(offset=200)
        attach_workflow(b, self.wf)

        # Step 1: custodian approves
        decide(b, self.custodian, approve=True, comment="Looks good")
        b.refresh_from_db()
        self.assertEqual(b.status, "pending")  # still pending, more steps
        approvals = list(b.approvals.order_by("order"))
        self.assertEqual(approvals[0].status, Approval.Status.APPROVED)
        self.assertEqual(approvals[1].status, Approval.Status.PENDING)  # activated

        # Step 2: dept head approves → booking confirmed
        decide(b, self.dept_head, approve=True, comment="Approved")
        b.refresh_from_db()
        self.assertEqual(b.status, "confirmed")

    def test_reject_at_first_step(self):
        b = self._fresh_booking(offset=300)
        attach_workflow(b, self.wf)

        decide(b, self.custodian, approve=False, comment="Not available")
        b.refresh_from_db()
        self.assertEqual(b.status, "rejected")
        self.assertEqual(b.approvals.filter(status=Approval.Status.REJECTED).count(), 1)

    def test_reject_at_second_step(self):
        b = self._fresh_booking(offset=400)
        attach_workflow(b, self.wf)

        decide(b, self.custodian, approve=True)
        decide(b, self.dept_head, approve=False, comment="Denied")
        b.refresh_from_db()
        self.assertEqual(b.status, "rejected")

    def test_wrong_role_cannot_decide(self):
        """A user without the right role for the current step gets 403."""
        from apps.bookings.exceptions import BookingError

        b = self._fresh_booking(offset=500)
        attach_workflow(b, self.wf)

        # Dept head tries to decide step 1 (custodian step)
        with self.assertRaises(BookingError) as ctx:
            decide(b, self.dept_head, approve=True)
        self.assertEqual(ctx.exception.http_status, 403)

    def test_admin_can_decide_any_step(self):
        """Superuser / admin can decide any approval step."""
        b = self._fresh_booking(offset=600)
        attach_workflow(b, self.wf)

        decide(b, self.admin, approve=True)  # step 1
        decide(b, self.admin, approve=True)  # step 2
        b.refresh_from_db()
        self.assertEqual(b.status, "confirmed")


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class QueueForTests(TestCase):
    """Test queue_for() returns only approvals the given user can act on."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(code="EE", name="Electrical")
        cls.rt = ResourceType.objects.create(name="Lab-Q", slug="lab-q")
        cls.loc = Location.objects.create(building="B3")
        cls.resource = Resource.objects.create(
            type=cls.rt, code="LAB-Q-01", name="Lab Q1", location=cls.loc, department=cls.dept
        )

        cls.requester = User.objects.create_user("req_q", password="p", role=Role.STUDENT, department=cls.dept)
        cls.custodian = User.objects.create_user("cust_q", password="p", role=Role.CUSTODIAN, department=cls.dept)
        cls.resource.custodians.add(cls.custodian)
        cls.dept_head = User.objects.create_user("dh_q", password="p", role=Role.DEPT_HEAD, department=cls.dept)
        cls.fm = User.objects.create_user("fm_q", password="p", role=Role.FACILITY_MANAGER)
        cls.admin = User.objects.create_user("adm_q", password="p", role=Role.ADMIN, is_superuser=True)

        # 1-step custodian workflow
        cls.wf = ApprovalWorkflow.objects.create(name="1-step cust", resource_type=cls.rt, priority=5)
        ApprovalStep.objects.create(workflow=cls.wf, order=1, name="Custodian Check", approver_role="custodian")

    def test_custodian_sees_their_pending(self):
        b = _make_booking(self.resource, self.requester, start_offset=700, status="pending")
        attach_workflow(b, self.wf)
        queue = queue_for(self.custodian)
        self.assertEqual(queue.count(), 1)

    def test_unrelated_user_empty_queue(self):
        b = _make_booking(self.resource, self.requester, start_offset=800, status="pending")
        attach_workflow(b, self.wf)
        # facility_manager has no custodian-step items
        queue = queue_for(self.fm)
        self.assertEqual(queue.count(), 0)

    def test_admin_sees_everything(self):
        b = _make_booking(self.resource, self.requester, start_offset=900, status="pending")
        attach_workflow(b, self.wf)
        queue = queue_for(self.admin)
        self.assertGreaterEqual(queue.count(), 1)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class ApproversForTests(TestCase):
    """Test approvers_for() returns correct users by role."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(code="ME", name="Mechanical")
        cls.rt = ResourceType.objects.create(name="Workshop-AF", slug="workshop-af")
        cls.loc = Location.objects.create(building="B4")
        cls.resource = Resource.objects.create(
            type=cls.rt, code="WS-AF-01", name="Workshop AF1", location=cls.loc, department=cls.dept
        )

        cls.custodian = User.objects.create_user("cust_af", password="p", role=Role.CUSTODIAN, department=cls.dept)
        cls.resource.custodians.add(cls.custodian)
        cls.dh = User.objects.create_user("dh_af", password="p", role=Role.DEPT_HEAD, department=cls.dept)
        cls.dept.head = cls.dh
        cls.dept.save()
        cls.fm = User.objects.create_user("fm_af", password="p", role=Role.FACILITY_MANAGER)

    def test_custodian_approvers(self):
        result = approvers_for(self.resource, Role.CUSTODIAN)
        self.assertIn(self.custodian, result)

    def test_dept_head_approvers(self):
        result = approvers_for(self.resource, Role.DEPT_HEAD)
        self.assertIn(self.dh, result)

    def test_facility_manager_approvers(self):
        result = approvers_for(self.resource, Role.FACILITY_MANAGER)
        self.assertIn(self.fm, result)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class CanDecideTests(TestCase):
    """Test can_decide() permission checks."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(code="PH", name="Physics")
        cls.rt = ResourceType.objects.create(name="Lab-CD", slug="lab-cd")
        cls.loc = Location.objects.create(building="B5")
        cls.resource = Resource.objects.create(
            type=cls.rt, code="LAB-CD-01", name="Lab CD1", location=cls.loc, department=cls.dept
        )
        cls.requester = User.objects.create_user("req_cd", password="p", role=Role.STUDENT, department=cls.dept)
        cls.custodian = User.objects.create_user("cust_cd", password="p", role=Role.CUSTODIAN, department=cls.dept)
        cls.resource.custodians.add(cls.custodian)
        cls.dh = User.objects.create_user("dh_cd", password="p", role=Role.DEPT_HEAD, department=cls.dept)
        cls.other_dh = User.objects.create_user(
            "dh_other",
            password="p",
            role=Role.DEPT_HEAD,
            department=Department.objects.create(code="CH", name="Chemistry"),
        )
        cls.admin = User.objects.create_user("adm_cd", password="p", role=Role.ADMIN, is_superuser=True)

    def _make_approval(self, role, offset):
        b = _make_booking(self.resource, self.requester, start_offset=offset, status="pending")
        return Approval.objects.create(booking=b, order=1, step_name="Test", approver_role=role, status="pending")

    def test_custodian_can_decide_custodian_step(self):
        a = self._make_approval(Role.CUSTODIAN, 1000)
        self.assertTrue(can_decide(self.custodian, a))

    def test_dept_head_can_decide_own_dept(self):
        a = self._make_approval(Role.DEPT_HEAD, 1100)
        self.assertTrue(can_decide(self.dh, a))

    def test_dept_head_cannot_decide_other_dept(self):
        a = self._make_approval(Role.DEPT_HEAD, 1200)
        self.assertFalse(can_decide(self.other_dh, a))

    def test_admin_can_decide_anything(self):
        a = self._make_approval(Role.CUSTODIAN, 1300)
        self.assertTrue(can_decide(self.admin, a))

    def test_student_cannot_decide(self):
        a = self._make_approval(Role.CUSTODIAN, 1400)
        self.assertFalse(can_decide(self.requester, a))


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class WorkflowCRUDApiTests(TestCase):
    """Test /api/workflows CRUD via WorkflowViewSet."""

    @classmethod
    def setUpTestData(cls):
        cls.rt = ResourceType.objects.create(name="Room-WF", slug="room-wf")
        cls.admin = User.objects.create_user("adm_wf", password="p", role=Role.ADMIN, is_superuser=True)
        cls.student = User.objects.create_user("stu_wf", password="p", role=Role.STUDENT)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_create_workflow_with_steps(self):
        resp = self.client.post(
            "/api/workflows",
            {
                "name": "New WF",
                "resource_type": self.rt.pk,
                "steps": [
                    {"name": "Step A", "approver_role": "custodian", "sla_hours": 12},
                    {"name": "Step B", "approver_role": "dept_head", "sla_hours": 24},
                ],
            },
            format="json",
        )
        self.assertEqual(resp.status_code, 201)
        data = resp.json()
        self.assertEqual(data["name"], "New WF")
        self.assertEqual(len(data["steps"]), 2)
        # Steps should be auto-ordered 1, 2
        self.assertEqual(data["steps"][0]["order"], 1)
        self.assertEqual(data["steps"][1]["order"], 2)

    def test_list_workflows(self):
        ApprovalWorkflow.objects.create(name="WF List", resource_type=self.rt)
        resp = self.client.get("/api/workflows")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 1)

    def test_update_workflow(self):
        wf = ApprovalWorkflow.objects.create(name="Old Name", resource_type=self.rt)
        resp = self.client.patch(f"/api/workflows/{wf.pk}", {"name": "New Name"}, format="json")
        self.assertEqual(resp.status_code, 200)
        wf.refresh_from_db()
        self.assertEqual(wf.name, "New Name")

    def test_delete_workflow(self):
        wf = ApprovalWorkflow.objects.create(name="To Delete", resource_type=self.rt)
        resp = self.client.delete(f"/api/workflows/{wf.pk}")
        self.assertEqual(resp.status_code, 204)
        self.assertFalse(ApprovalWorkflow.objects.filter(pk=wf.pk).exists())

    def test_student_cannot_create_workflow(self):
        self.client.force_authenticate(user=self.student)
        resp = self.client.post(
            "/api/workflows",
            {"name": "Sneaky", "resource_type": self.rt.pk, "steps": []},
            format="json",
        )
        self.assertIn(resp.status_code, [401, 403])


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class ApprovalQueueApiTests(TestCase):
    """Test the /api/approvals/queue endpoint."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(code="IT", name="Information Technology")
        cls.rt = ResourceType.objects.create(name="Room-AQ", slug="room-aq")
        cls.loc = Location.objects.create(building="B6")
        cls.resource = Resource.objects.create(
            type=cls.rt, code="ROOM-AQ-01", name="Room AQ1", location=cls.loc, department=cls.dept
        )
        cls.requester = User.objects.create_user("req_aq", password="p", role=Role.STUDENT, department=cls.dept)
        cls.custodian = User.objects.create_user("cust_aq", password="p", role=Role.CUSTODIAN, department=cls.dept)
        cls.resource.custodians.add(cls.custodian)

        cls.wf = ApprovalWorkflow.objects.create(name="AQ WF", resource_type=cls.rt, priority=5)
        ApprovalStep.objects.create(workflow=cls.wf, order=1, name="Cust AQ", approver_role="custodian")

    def test_queue_returns_pending_for_custodian(self):
        b = _make_booking(self.resource, self.requester, start_offset=1500, status="pending")
        attach_workflow(b, self.wf)

        client = APIClient()
        client.force_authenticate(user=self.custodian)
        resp = client.get("/api/approvals/queue")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertGreaterEqual(len(data), 1)
        self.assertIn("current_step", data[0])

    def test_queue_empty_for_unrelated_user(self):
        b = _make_booking(self.resource, self.requester, start_offset=1600, status="pending")
        attach_workflow(b, self.wf)

        other = User.objects.create_user("other_aq", password="p", role=Role.STUDENT)
        client = APIClient()
        client.force_authenticate(user=other)
        resp = client.get("/api/approvals/queue")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()), 0)

    def test_queue_unauthenticated_401(self):
        client = APIClient()
        resp = client.get("/api/approvals/queue")
        self.assertEqual(resp.status_code, 401)
