"""
Tests for apps.analytics — dashboard, utilisation, heatmap, and public stats endpoints.

Covers:
  • UtilisationSnapshot model
  • /api/public/stats — public (no auth required)
  • /api/analytics/dashboard — manager-only
  • /api/analytics/utilisation — manager-only
  • /api/analytics/heatmap — manager-only
  • /api/analytics/noshows — manager-only
  • /api/analytics/demand — manager-only
  • /api/analytics/approvals — manager-only
  • /api/analytics/downtime — manager-only
  • /api/analytics/quotas — manager-only
  • Student forbidden from analytics endpoints
"""

from datetime import date, timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Department, Role, User
from apps.catalogue.models import Location, Resource, ResourceType

from .models import UtilisationSnapshot


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class UtilisationSnapshotTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rt = ResourceType.objects.create(name="Room-AN", slug="room-an")
        cls.loc = Location.objects.create(building="B-AN")
        cls.res = Resource.objects.create(type=cls.rt, code="RM-AN-01", name="Room AN1", location=cls.loc)

    def test_snapshot_creation(self):
        s = UtilisationSnapshot.objects.create(
            resource=self.res, date=date.today(),
            available_minutes=480, booked_minutes=120, used_minutes=100,
        )
        self.assertEqual(s.available_minutes, 480)

    def test_unique_together(self):
        from django.db import IntegrityError
        UtilisationSnapshot.objects.create(resource=self.res, date=date.today())
        with self.assertRaises(IntegrityError):
            UtilisationSnapshot.objects.create(resource=self.res, date=date.today())


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class PublicStatsTests(TestCase):
    """The /api/public/stats endpoint is accessible without authentication."""

    @classmethod
    def setUpTestData(cls):
        cls.rt = ResourceType.objects.create(name="Room-PS", slug="room-ps")
        cls.loc = Location.objects.create(building="B-PS")
        Resource.objects.create(type=cls.rt, code="RM-PS-01", name="Room PS1", location=cls.loc)

    def test_public_stats_no_auth(self):
        client = APIClient()
        resp = client.get("/api/public/stats")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("resources", data)
        self.assertIn("types", data)
        self.assertIn("bookings_30d", data)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class AnalyticsApiTests(TestCase):
    """Test all analytics endpoints — manager-only access."""

    @classmethod
    def setUpTestData(cls):
        cls.rt = ResourceType.objects.create(name="Room-AAI", slug="room-aai")
        cls.loc = Location.objects.create(building="B-AAI")
        Resource.objects.create(type=cls.rt, code="RM-AAI-01", name="Room AAI1", location=cls.loc)
        cls.admin = User.objects.create_user("adm_aai", password="p", role=Role.ADMIN, is_superuser=True)
        cls.student = User.objects.create_user("stu_aai", password="p", role=Role.STUDENT)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_dashboard(self):
        resp = self.client.get("/api/analytics/dashboard")
        self.assertEqual(resp.status_code, 200)

    def test_utilisation(self):
        resp = self.client.get("/api/analytics/utilisation")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("by_resource", resp.json())

    def test_heatmap(self):
        resp = self.client.get("/api/analytics/heatmap")
        self.assertEqual(resp.status_code, 200)

    def test_noshows(self):
        resp = self.client.get("/api/analytics/noshows")
        self.assertEqual(resp.status_code, 200)

    def test_demand(self):
        resp = self.client.get("/api/analytics/demand")
        self.assertEqual(resp.status_code, 200)

    def test_approvals(self):
        resp = self.client.get("/api/analytics/approvals")
        self.assertEqual(resp.status_code, 200)

    def test_downtime(self):
        resp = self.client.get("/api/analytics/downtime")
        self.assertEqual(resp.status_code, 200)

    def test_quotas(self):
        resp = self.client.get("/api/analytics/quotas")
        self.assertEqual(resp.status_code, 200)

    # ── Permission checks ──
    def test_student_forbidden_dashboard(self):
        self.client.force_authenticate(user=self.student)
        resp = self.client.get("/api/analytics/dashboard")
        self.assertIn(resp.status_code, [401, 403])

    def test_student_forbidden_utilisation(self):
        self.client.force_authenticate(user=self.student)
        resp = self.client.get("/api/analytics/utilisation")
        self.assertIn(resp.status_code, [401, 403])

    def test_student_forbidden_heatmap(self):
        self.client.force_authenticate(user=self.student)
        resp = self.client.get("/api/analytics/heatmap")
        self.assertIn(resp.status_code, [401, 403])
