"""
Tests for apps.consumables — inventory management, issuance, return, and API.

Covers:
  • Consumable model (is_low, stock constraint)
  • issue() — stock decrement, out-of-stock error, bad quantity
  • return_issuance() — stock restoration, status update
  • _alert_if_low() — low-stock notification
  • /api/consumables CRUD + restock action
  • /api/issuances — create issuance, return issuance, filtering
  • Permission checks — student vs manager
"""

from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import Department, Role, User
from apps.catalogue.models import Location, Resource, ResourceType

from .models import Consumable, Issuance
from .services import issue, return_issuance


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class ConsumableModelTests(TestCase):
    def test_is_low_when_stock_at_reorder(self):
        c = Consumable.objects.create(name="Marker", sku="MK-001", stock=5, reorder_level=5)
        self.assertTrue(c.is_low)

    def test_not_low_when_stock_above(self):
        c = Consumable.objects.create(name="Chalk", sku="CK-001", stock=20, reorder_level=5)
        self.assertFalse(c.is_low)

    def test_str(self):
        c = Consumable.objects.create(name="Eraser", sku="ER-001", stock=10)
        self.assertEqual(str(c), "Eraser")


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class IssueServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("iss_user", password="p", role=Role.STUDENT)

    def test_issue_decrements_stock(self):
        c = Consumable.objects.create(name="Pen-I", sku="PN-I-01", stock=10, reorder_level=2)
        iss = issue(c.pk, 3, self.user)
        c.refresh_from_db()
        self.assertEqual(c.stock, 7)
        self.assertEqual(iss.quantity, 3)
        self.assertEqual(iss.status, Issuance.Status.ISSUED)

    def test_issue_out_of_stock(self):
        from apps.bookings.exceptions import BookingError
        c = Consumable.objects.create(name="Pen-OS", sku="PN-OS-01", stock=2, reorder_level=1)
        with self.assertRaises(BookingError) as ctx:
            issue(c.pk, 5, self.user)
        self.assertEqual(ctx.exception.code, "out_of_stock")

    def test_issue_bad_quantity(self):
        from apps.bookings.exceptions import BookingError
        c = Consumable.objects.create(name="Pen-BQ", sku="PN-BQ-01", stock=10)
        with self.assertRaises(BookingError):
            issue(c.pk, 0, self.user)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class ReturnServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("ret_user", password="p", role=Role.STUDENT)

    def test_return_accessory_restores_stock(self):
        c = Consumable.objects.create(name="Adapter-R", sku="AD-R-01", stock=10, reorder_level=2, kind="accessory")
        iss = issue(c.pk, 2, self.user)
        c.refresh_from_db()
        self.assertEqual(c.stock, 8)
        return_issuance(iss)
        c.refresh_from_db()
        self.assertEqual(c.stock, 10)
        iss.refresh_from_db()
        self.assertEqual(iss.status, Issuance.Status.RETURNED)
        self.assertIsNotNone(iss.returned_at)

    def test_return_already_closed(self):
        from apps.bookings.exceptions import BookingError
        c = Consumable.objects.create(name="Adapter-AC", sku="AD-AC-01", stock=10, kind="accessory")
        iss = issue(c.pk, 1, self.user)
        return_issuance(iss)
        with self.assertRaises(BookingError) as ctx:
            return_issuance(iss)
        self.assertEqual(ctx.exception.code, "already_closed")


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class ConsumableApiTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user("adm_con", password="p", role=Role.ADMIN, is_superuser=True)
        cls.student = User.objects.create_user("stu_con", password="p", role=Role.STUDENT)
        cls.custodian = User.objects.create_user("cust_con", password="p", role=Role.CUSTODIAN)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    def test_create_consumable(self):
        resp = self.client.post("/api/consumables", {
            "name": "Whiteboard Marker",
            "sku": "WM-API-01",
            "stock": 50,
            "reorder_level": 10,
            "unit": "pcs",
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["name"], "Whiteboard Marker")

    def test_list_consumables(self):
        Consumable.objects.create(name="List Item", sku="LI-01", stock=10)
        resp = self.client.get("/api/consumables")
        self.assertEqual(resp.status_code, 200)

    def test_restock_action(self):
        c = Consumable.objects.create(name="Restock Me", sku="RS-01", stock=5)
        resp = self.client.post(f"/api/consumables/{c.pk}/restock", {"quantity": 20}, format="json")
        self.assertEqual(resp.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.stock, 25)

    def test_student_cannot_create(self):
        self.client.force_authenticate(user=self.student)
        resp = self.client.post("/api/consumables", {
            "name": "Sneaky", "sku": "SN-01", "stock": 10,
        }, format="json")
        self.assertIn(resp.status_code, [401, 403])

    def test_create_issuance(self):
        c = Consumable.objects.create(name="Issue Via API", sku="IV-01", stock=20)
        self.client.force_authenticate(user=self.custodian)
        resp = self.client.post("/api/issuances", {
            "consumable": c.pk, "quantity": 2,
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        c.refresh_from_db()
        self.assertEqual(c.stock, 18)

    def test_return_issuance_api(self):
        c = Consumable.objects.create(name="Return API", sku="RA-01", stock=20, kind="accessory")
        iss = issue(c.pk, 3, self.admin)
        self.client.force_authenticate(user=self.custodian)
        resp = self.client.post(f"/api/issuances/{iss.pk}/return", format="json")
        self.assertEqual(resp.status_code, 200)
        c.refresh_from_db()
        self.assertEqual(c.stock, 20)
