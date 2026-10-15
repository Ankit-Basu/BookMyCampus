"""
Tests for apps.maintenance — maintenance window scheduling, breakdown reporting, resolve, cancel.

Covers:
  • schedule() — creates MaintenanceWindow + BookingSlot, notifies custodians
  • report_breakdown() — marks resource as "down"
  • resolve() — closes window early, restores resource status
  • cancel() — cancels window, removes slot, restores status
  • API: POST /api/maintenance, POST /api/maintenance/report, resolve, cancel
  • Permission checks
"""

from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from psycopg.types.range import Range
from rest_framework.test import APIClient

from apps.accounts.models import Department, Role, User
from apps.bookings.models import BookingSlot
from apps.catalogue.models import Location, Resource, ResourceType

from .models import MaintenanceWindow
from .services import cancel, report_breakdown, resolve, schedule


def _ts(offset_hours=0):
    return timezone.now() + timedelta(hours=offset_hours)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class ScheduleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rt = ResourceType.objects.create(name="Room-MT", slug="room-mt")
        cls.loc = Location.objects.create(building="B-MT")
        cls.res = Resource.objects.create(type=cls.rt, code="RM-MT-01", name="Room MT1", location=cls.loc)
        cls.admin = User.objects.create_user("adm_mt", password="p", role=Role.ADMIN, is_superuser=True)

    def test_schedule_creates_window_and_slot(self):
        start = _ts(100)
        end = _ts(104)
        w = schedule(self.res, start, end, title="HVAC Repair")
        self.assertIsNotNone(w)
        self.assertEqual(w.title, "HVAC Repair")
        self.assertEqual(w.status, MaintenanceWindow.Status.PLANNED)
        # Slot should exist
        self.assertTrue(BookingSlot.objects.filter(maintenance=w).exists())

    def test_invalid_period_raises(self):
        from apps.bookings.exceptions import BookingError
        with self.assertRaises(BookingError):
            schedule(self.res, _ts(200), _ts(199), title="Bad")


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class BreakdownTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rt = ResourceType.objects.create(name="Room-BD", slug="room-bd")
        cls.loc = Location.objects.create(building="B-BD")
        cls.res = Resource.objects.create(type=cls.rt, code="RM-BD-01", name="Room BD1", location=cls.loc)
        cls.user = User.objects.create_user("bd_user", password="p", role=Role.STUDENT)

    def test_breakdown_marks_resource_down(self):
        w = report_breakdown(self.res, self.user, "Broken projector")
        self.res.refresh_from_db()
        self.assertEqual(self.res.status, Resource.Status.DOWN)
        self.assertEqual(w.kind, MaintenanceWindow.Kind.BREAKDOWN)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class ResolveAndCancelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rt = ResourceType.objects.create(name="Room-RC", slug="room-rc")
        cls.loc = Location.objects.create(building="B-RC")
        cls.res = Resource.objects.create(type=cls.rt, code="RM-RC-01", name="Room RC1", location=cls.loc)
        cls.user = User.objects.create_user("rc_user", password="p", role=Role.STUDENT)

    def test_resolve_sets_done_and_restores_status(self):
        w = report_breakdown(self.res, self.user, "Fix AC")
        self.res.refresh_from_db()
        self.assertEqual(self.res.status, Resource.Status.DOWN)

        resolve(w)
        w.refresh_from_db()
        self.assertEqual(w.status, MaintenanceWindow.Status.DONE)
        self.assertIsNotNone(w.resolved_at)
        self.res.refresh_from_db()
        self.assertEqual(self.res.status, Resource.Status.ACTIVE)

    def test_cancel_removes_slot_and_restores_status(self):
        w = report_breakdown(self.res, self.user, "False alarm")
        self.res.refresh_from_db()
        self.assertEqual(self.res.status, Resource.Status.DOWN)

        cancel(w)
        w.refresh_from_db()
        self.assertEqual(w.status, MaintenanceWindow.Status.CANCELLED)
        self.assertFalse(BookingSlot.objects.filter(maintenance=w).exists())
        self.res.refresh_from_db()
        self.assertEqual(self.res.status, Resource.Status.ACTIVE)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class MaintenanceApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rt = ResourceType.objects.create(name="Room-MA", slug="room-ma")
        cls.loc = Location.objects.create(building="B-MA")
        cls.res = Resource.objects.create(type=cls.rt, code="RM-MA-01", name="Room MA1", location=cls.loc)
        cls.admin = User.objects.create_user("adm_ma", password="p", role=Role.ADMIN, is_superuser=True)
        cls.student = User.objects.create_user("stu_ma", password="p", role=Role.STUDENT)
        cls.custodian = User.objects.create_user("cust_ma", password="p", role=Role.CUSTODIAN)

    def setUp(self):
        self.client = APIClient()

    def test_list_maintenance(self):
        self.client.force_authenticate(user=self.student)
        resp = self.client.get("/api/maintenance")
        self.assertEqual(resp.status_code, 200)

    def test_schedule_maintenance_as_manager(self):
        self.client.force_authenticate(user=self.custodian)
        start = _ts(300)
        end = _ts(304)
        resp = self.client.post("/api/maintenance", {
            "resource": self.res.pk,
            "start": start.isoformat(),
            "end": end.isoformat(),
            "title": "Plumbing fix",
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["title"], "Plumbing fix")

    def test_student_cannot_schedule(self):
        self.client.force_authenticate(user=self.student)
        resp = self.client.post("/api/maintenance", {
            "resource": self.res.pk,
            "start": _ts(400).isoformat(),
            "end": _ts(404).isoformat(),
            "title": "Sneaky",
        }, format="json")
        self.assertIn(resp.status_code, [401, 403])

    def test_report_breakdown_any_user(self):
        self.client.force_authenticate(user=self.student)
        resp = self.client.post("/api/maintenance/report", {
            "resource": self.res.pk,
            "title": "Broken light",
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.res.refresh_from_db()
        self.assertEqual(self.res.status, Resource.Status.DOWN)
        # Restore for other tests
        self.res.status = Resource.Status.ACTIVE
        self.res.save()

    def test_resolve_maintenance(self):
        self.client.force_authenticate(user=self.custodian)
        w = schedule(self.res, _ts(500), _ts(504), title="API resolve test")
        resp = self.client.post(f"/api/maintenance/{w.pk}/resolve", format="json")
        self.assertEqual(resp.status_code, 200)

    def test_cancel_maintenance(self):
        self.client.force_authenticate(user=self.custodian)
        w = schedule(self.res, _ts(600), _ts(604), title="API cancel test")
        resp = self.client.post(f"/api/maintenance/{w.pk}/cancel", format="json")
        self.assertEqual(resp.status_code, 200)
        w.refresh_from_db()
        self.assertEqual(w.status, MaintenanceWindow.Status.CANCELLED)
