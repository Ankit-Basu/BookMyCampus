"""
Tests for apps.notifications — notification model, service layer, and API endpoints.

Covers:
  • Notification model & ordering
  • notify() — creates in-app notification
  • notify_many() — deduplicates by user pk
  • /api/notifications — list with unread count
  • /api/notifications/<id>/read — mark single read
  • /api/notifications/read-all — mark all read
  • Unauthenticated 401
"""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import Role, User

from .models import Notification
from .services import notify, notify_many


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class NotifyServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("notif_u1", password="p", role=Role.STUDENT)
        cls.user2 = User.objects.create_user("notif_u2", password="p", role=Role.FACULTY)

    def test_notify_creates_notification(self):
        n = notify(self.user, Notification.Kind.INFO, "Hello", "World", link="/test")
        self.assertIsNotNone(n)
        self.assertEqual(n.user, self.user)
        self.assertEqual(n.kind, Notification.Kind.INFO)
        self.assertEqual(n.title, "Hello")
        self.assertEqual(n.body, "World")
        self.assertEqual(n.link, "/test")
        self.assertIsNone(n.read_at)

    def test_notify_none_user_returns_none(self):
        result = notify(None, Notification.Kind.INFO, "Nope")
        self.assertIsNone(result)

    def test_notify_many_deduplicates(self):
        before = Notification.objects.filter(user=self.user).count()
        notify_many([self.user, self.user, self.user], Notification.Kind.INFO, "Dedup test")
        after = Notification.objects.filter(user=self.user, title="Dedup test").count()
        self.assertEqual(after - 0, 1)  # Only one notification created despite 3 users

    def test_notify_many_multiple_users(self):
        notify_many([self.user, self.user2], Notification.Kind.REMINDER, "Multi test")
        self.assertEqual(Notification.objects.filter(title="Multi test").count(), 2)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class NotificationModelTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("notif_model", password="p", role=Role.STUDENT)

    def test_ordering_newest_first(self):
        n1 = Notification.objects.create(user=self.user, kind="info", title="First")
        n2 = Notification.objects.create(user=self.user, kind="info", title="Second")
        notifs = list(Notification.objects.filter(user=self.user))
        self.assertEqual(notifs[0].pk, n2.pk)  # newest first


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class NotificationApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("notif_api", password="p", role=Role.STUDENT)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_list_returns_unread_count(self):
        Notification.objects.create(user=self.user, kind="info", title="Unread 1")
        Notification.objects.create(user=self.user, kind="info", title="Unread 2")
        resp = self.client.get("/api/notifications")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("unread", data)
        self.assertGreaterEqual(data["unread"], 2)
        self.assertIn("items", data)

    def test_mark_single_read(self):
        n = Notification.objects.create(user=self.user, kind="info", title="To read")
        resp = self.client.post(f"/api/notifications/{n.pk}/read")
        self.assertEqual(resp.status_code, 200)
        n.refresh_from_db()
        self.assertIsNotNone(n.read_at)

    def test_mark_all_read(self):
        Notification.objects.create(user=self.user, kind="info", title="All 1")
        Notification.objects.create(user=self.user, kind="info", title="All 2")
        resp = self.client.post("/api/notifications/read-all")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(Notification.objects.filter(user=self.user, read_at__isnull=True).count(), 0)

    def test_unauthenticated_401(self):
        client = APIClient()
        resp = client.get("/api/notifications")
        self.assertEqual(resp.status_code, 401)
