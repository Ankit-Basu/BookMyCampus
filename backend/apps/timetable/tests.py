"""
Tests for apps.timetable — timetable publishing, versioning, and API endpoints.

Covers:
  • TimetableVersion model + unique constraint on is_current
  • TimetableEntry model
  • validate_payload() — unknown resource detection, internal clash detection
  • publish() — creates version, entries, and booking slots; idempotent re-publish
  • /api/timetable/publish — webhook with token auth
  • /api/timetable/current — returns current entries
  • /api/timetable/versions — lists versions
"""

from datetime import date, timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Role, User
from apps.bookings.models import BookingSlot
from apps.catalogue.models import Location, Resource, ResourceType

from .models import TimetableEntry, TimetableVersion
from .services import checksum, publish, validate_payload


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    TIMETABLE_WEBHOOK_TOKEN="test-secret-token",
)
class TimetableModelTests(TestCase):
    def test_version_str(self):
        v = TimetableVersion.objects.create(label="Spring 2026", term_start=date(2026, 1, 6), term_end=date(2026, 4, 30))
        self.assertEqual(str(v), "Spring 2026")

    def test_ordering_newest_first(self):
        v1 = TimetableVersion.objects.create(label="V1", term_start=date(2026, 1, 6), term_end=date(2026, 4, 30))
        v2 = TimetableVersion.objects.create(label="V2", term_start=date(2026, 1, 6), term_end=date(2026, 4, 30))
        versions = list(TimetableVersion.objects.all())
        self.assertEqual(versions[0].pk, v2.pk)

    def test_unique_current_constraint(self):
        from django.db import IntegrityError
        TimetableVersion.objects.create(label="C1", term_start=date(2026, 1, 6), term_end=date(2026, 4, 30), is_current=True)
        with self.assertRaises(IntegrityError):
            TimetableVersion.objects.create(label="C2", term_start=date(2026, 1, 6), term_end=date(2026, 4, 30), is_current=True)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    TIMETABLE_WEBHOOK_TOKEN="test-secret-token",
)
class ValidatePayloadTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rt = ResourceType.objects.create(name="Room-TT", slug="room-tt")
        cls.loc = Location.objects.create(building="B-TT")
        cls.res = Resource.objects.create(type=cls.rt, code="RM-TT-01", name="Room TT1", location=cls.loc)

    def test_unknown_resource_raises(self):
        from apps.bookings.exceptions import BookingError
        payload = {"entries": [{"resource_code": "FAKE-99", "weekday": 0, "start": "09:00", "end": "10:00", "course_code": "CS101"}]}
        with self.assertRaises(BookingError) as ctx:
            validate_payload(payload)
        self.assertEqual(ctx.exception.code, "unknown_resources")

    def test_internal_clash_raises(self):
        from apps.bookings.exceptions import BookingError
        payload = {"entries": [
            {"resource_code": "RM-TT-01", "weekday": 0, "start": "09:00", "end": "10:00", "course_code": "CS101"},
            {"resource_code": "RM-TT-01", "weekday": 0, "start": "09:30", "end": "10:30", "course_code": "CS102"},
        ]}
        with self.assertRaises(BookingError) as ctx:
            validate_payload(payload)
        self.assertEqual(ctx.exception.code, "timetable_clash")

    def test_valid_payload_returns_resources(self):
        payload = {"entries": [
            {"resource_code": "RM-TT-01", "weekday": 0, "start": "09:00", "end": "10:00", "course_code": "CS101"},
        ]}
        resources = validate_payload(payload)
        self.assertIn("RM-TT-01", resources)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    TIMETABLE_WEBHOOK_TOKEN="test-secret-token",
)
class PublishServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rt = ResourceType.objects.create(name="Room-PB", slug="room-pb")
        cls.loc = Location.objects.create(building="B-PB")
        cls.res = Resource.objects.create(type=cls.rt, code="RM-PB-01", name="Room PB1", location=cls.loc)

    def _payload(self, label="Test TT"):
        today = timezone.localdate()
        return {
            "label": label,
            "term_start": str(today),
            "term_end": str(today + timedelta(days=14)),
            "entries": [
                {"resource_code": "RM-PB-01", "weekday": 0, "start": "09:00", "end": "10:00", "course_code": "CS101"},
            ],
        }

    def test_publish_creates_version_and_entries(self):
        version, changed = publish(self._payload())
        self.assertTrue(changed)
        self.assertTrue(version.is_current)
        self.assertEqual(version.entries.count(), 1)

    def test_idempotent_republish(self):
        p = self._payload("Idem")
        v1, c1 = publish(p)
        v2, c2 = publish(p)
        self.assertTrue(c1)
        self.assertFalse(c2)
        self.assertEqual(v1.pk, v2.pk)

    def test_new_publish_replaces_current(self):
        p1 = self._payload("V1")
        v1, _ = publish(p1)
        self.assertTrue(v1.is_current)

        p2 = self._payload("V2")
        p2["entries"][0]["course_code"] = "CS202"  # different content
        v2, _ = publish(p2)
        v1.refresh_from_db()
        self.assertFalse(v1.is_current)
        self.assertTrue(v2.is_current)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    TIMETABLE_WEBHOOK_TOKEN="test-secret-token",
)
class TimetableApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rt = ResourceType.objects.create(name="Room-TA", slug="room-ta")
        cls.loc = Location.objects.create(building="B-TA")
        cls.res = Resource.objects.create(type=cls.rt, code="RM-TA-01", name="Room TA1", location=cls.loc)
        cls.admin = User.objects.create_user("adm_ta", password="p", role=Role.ADMIN, is_superuser=True)
        cls.fm = User.objects.create_user("fm_ta", password="p", role=Role.FACILITY_MANAGER)
        cls.student = User.objects.create_user("stu_ta", password="p", role=Role.STUDENT)

    def setUp(self):
        self.client = APIClient()

    def _payload(self):
        today = timezone.localdate()
        return {
            "label": "API Test TT",
            "term_start": str(today),
            "term_end": str(today + timedelta(days=14)),
            "entries": [
                {"resource_code": "RM-TA-01", "weekday": 0, "start": "09:00", "end": "10:00", "course_code": "CS301"},
            ],
        }

    def test_publish_with_token(self):
        resp = self.client.post(
            "/api/timetable/publish",
            self._payload(),
            format="json",
            HTTP_X_TIMETABLE_TOKEN="test-secret-token",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.json()["changed"])

    def test_publish_as_fm(self):
        self.client.force_authenticate(user=self.fm)
        resp = self.client.post("/api/timetable/publish", self._payload(), format="json")
        self.assertEqual(resp.status_code, 201)

    def test_publish_forbidden_for_student(self):
        self.client.force_authenticate(user=self.student)
        resp = self.client.post("/api/timetable/publish", self._payload(), format="json")
        self.assertEqual(resp.status_code, 403)

    def test_current_endpoint(self):
        publish(self._payload())
        self.client.force_authenticate(user=self.student)
        resp = self.client.get("/api/timetable/current")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("version", data)
        self.assertIn("entries", data)

    def test_versions_endpoint(self):
        self.client.force_authenticate(user=self.student)
        resp = self.client.get("/api/timetable/versions")
        self.assertEqual(resp.status_code, 200)
