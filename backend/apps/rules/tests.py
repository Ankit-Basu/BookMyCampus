"""
Tests for apps.rules — availability rules, blackouts, quotas, policy, and validation engine.

Covers:
  • AvailabilityRule model & constraints
  • rules_for() — resource-level rules override type-level
  • matching_rule() — weekday + time matching
  • merge() / subtract() / total_minutes() interval helpers
  • validate_request() — opening hours, duration, lead-time, blackout, capacity, role, restriction
  • Quota enforcement — user hours/week, active-bookings cap
  • Policy singleton
  • CRUD APIs: /api/availability-rules, /api/blackouts, /api/quotas, /api/policy
"""

from datetime import date, datetime, time, timedelta

from django.test import TestCase, override_settings
from django.utils import timezone
from psycopg.types.range import Range
from rest_framework.test import APIClient

from apps.accounts.models import Department, Role, User
from apps.bookings.exceptions import RuleViolation
from apps.bookings.models import Booking, BookingSlot
from apps.catalogue.models import Location, Resource, ResourceType

from .models import AvailabilityRule, Blackout, Policy, Quota
from .services import (
    blackouts_for,
    matching_rule,
    merge,
    open_windows,
    rules_for,
    subtract,
    total_minutes,
    validate_request,
)


def _ts(offset_hours=0):
    return timezone.now() + timedelta(hours=offset_hours)


# ─────────────────────────────── Interval helper tests ───────────────────────────────


class MergeTests(TestCase):
    def test_no_overlap(self):
        result = merge([(1, 3), (5, 7)])
        self.assertEqual(result, [(1, 3), (5, 7)])

    def test_overlap(self):
        result = merge([(1, 5), (3, 8)])
        self.assertEqual(result, [(1, 8)])

    def test_adjacent(self):
        result = merge([(1, 3), (3, 5)])
        self.assertEqual(result, [(1, 5)])

    def test_empty(self):
        self.assertEqual(merge([]), [])


class SubtractTests(TestCase):
    def test_cut_in_middle(self):
        result = subtract([(0, 10)], [(3, 5)])
        self.assertEqual(result, [(0, 3), (5, 10)])

    def test_cut_entire(self):
        result = subtract([(0, 10)], [(0, 10)])
        self.assertEqual(result, [])

    def test_no_cut(self):
        result = subtract([(0, 10)], [(20, 30)])
        self.assertEqual(result, [(0, 10)])


class TotalMinutesTests(TestCase):
    def test_single_interval(self):
        now = timezone.now()
        result = total_minutes([(now, now + timedelta(hours=2))])
        self.assertEqual(result, 120)

    def test_multiple_intervals(self):
        now = timezone.now()
        result = total_minutes([(now, now + timedelta(minutes=30)), (now + timedelta(hours=1), now + timedelta(hours=2))])
        self.assertEqual(result, 90)


# ─────────────────────────────── Rules lookup tests ───────────────────────────────


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class RulesForTests(TestCase):
    """Resource-level rules override type-level rules."""

    @classmethod
    def setUpTestData(cls):
        cls.rt = ResourceType.objects.create(name="Room-RF", slug="room-rf")
        cls.loc = Location.objects.create(building="B-RF")
        cls.res = Resource.objects.create(type=cls.rt, code="RM-RF-01", name="Room RF1", location=cls.loc)

        # Type-level rule
        cls.type_rule = AvailabilityRule.objects.create(
            resource_type=cls.rt, name="Type Hours",
            weekdays=[0, 1, 2, 3, 4], open_time=time(8, 0), close_time=time(20, 0),
        )
        # Resource-level rule (should override)
        cls.res_rule = AvailabilityRule.objects.create(
            resource=cls.res, name="Room Hours",
            weekdays=[0, 1, 2, 3, 4, 5], open_time=time(7, 0), close_time=time(22, 0),
        )

    def test_resource_rule_overrides_type(self):
        rules = rules_for(self.res)
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0], self.res_rule)

    def test_type_rule_used_when_no_resource_rule(self):
        res2 = Resource.objects.create(type=self.rt, code="RM-RF-02", name="Room RF2", location=self.loc)
        rules = rules_for(res2)
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0], self.type_rule)


# ─────────────────────────────── Matching rule tests ───────────────────────────────


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class MatchingRuleTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.rt = ResourceType.objects.create(name="Room-MR", slug="room-mr")
        cls.loc = Location.objects.create(building="B-MR")
        cls.res = Resource.objects.create(type=cls.rt, code="RM-MR-01", name="Room MR1", location=cls.loc)
        # Mon-Fri 08:00–20:00
        cls.rule = AvailabilityRule.objects.create(
            resource=cls.res, name="Weekday",
            weekdays=[0, 1, 2, 3, 4], open_time=time(8, 0), close_time=time(20, 0),
        )

    def test_match_within_hours(self):
        # Find next weekday
        now = timezone.now()
        local = timezone.localtime(now)
        # Advance to next Monday
        days_ahead = (0 - local.weekday()) % 7 or 7
        next_mon = local.replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
        start = timezone.make_aware(next_mon.replace(tzinfo=None), timezone.get_current_timezone())
        end = start + timedelta(hours=1)
        result = matching_rule(self.res, start, end)
        self.assertEqual(result, self.rule)

    def test_no_match_outside_hours(self):
        now = timezone.now()
        local = timezone.localtime(now)
        days_ahead = (0 - local.weekday()) % 7 or 7
        next_mon = local.replace(hour=21, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
        start = timezone.make_aware(next_mon.replace(tzinfo=None), timezone.get_current_timezone())
        end = start + timedelta(hours=1)
        result = matching_rule(self.res, start, end)
        self.assertIsNone(result)

    def test_no_match_on_weekend(self):
        now = timezone.now()
        local = timezone.localtime(now)
        # Advance to Saturday (weekday=5)
        days_ahead = (5 - local.weekday()) % 7 or 7
        next_sat = local.replace(hour=10, minute=0, second=0, microsecond=0) + timedelta(days=days_ahead)
        start = timezone.make_aware(next_sat.replace(tzinfo=None), timezone.get_current_timezone())
        end = start + timedelta(hours=1)
        result = matching_rule(self.res, start, end)
        self.assertIsNone(result)


# ─────────────────────────────── validate_request tests ───────────────────────────────


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class ValidateRequestTests(TestCase):
    """Test the core validation engine."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(code="VR", name="VR Dept")
        cls.rt = ResourceType.objects.create(name="Room-VR", slug="room-vr")
        cls.loc = Location.objects.create(building="B-VR")
        cls.res = Resource.objects.create(
            type=cls.rt, code="RM-VR-01", name="Room VR1", location=cls.loc,
            capacity=30, department=cls.dept,
        )
        cls.user = User.objects.create_user("u_vr", password="p", role=Role.STUDENT, department=cls.dept)

        # Mon-Fri 08:00–20:00, 30min-3h, 0 lead, 30 day window
        cls.rule = AvailabilityRule.objects.create(
            resource=cls.res, name="Std", weekdays=[0, 1, 2, 3, 4],
            open_time=time(8, 0), close_time=time(20, 0),
            min_duration_minutes=30, max_duration_minutes=180,
            min_lead_minutes=0, max_advance_days=30,
        )

    def _next_weekday_at(self, hour, minute=0, days_offset=1):
        """Return next weekday datetime at the given time, far enough in the future."""
        local = timezone.localtime(timezone.now())
        # Go to tomorrow + days_offset to ensure it's in the future
        target = local + timedelta(days=days_offset)
        while target.weekday() > 4:  # Skip weekends
            target += timedelta(days=1)
        target = target.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return timezone.make_aware(target.replace(tzinfo=None), timezone.get_current_timezone())

    def test_valid_request_passes(self):
        start = self._next_weekday_at(10)
        end = start + timedelta(hours=1)
        rule = validate_request(self.user, self.res, start, end)
        self.assertEqual(rule, self.rule)

    def test_end_before_start_raises(self):
        start = self._next_weekday_at(10)
        with self.assertRaises(RuleViolation) as ctx:
            validate_request(self.user, self.res, start, start - timedelta(hours=1))
        self.assertEqual(ctx.exception.code, "invalid_period")

    def test_out_of_service_resource(self):
        self.res.status = "down"
        self.res.save()
        start = self._next_weekday_at(10)
        end = start + timedelta(hours=1)
        with self.assertRaises(RuleViolation) as ctx:
            validate_request(self.user, self.res, start, end)
        self.assertEqual(ctx.exception.code, "resource_unavailable")
        self.res.status = "active"
        self.res.save()

    def test_over_capacity(self):
        start = self._next_weekday_at(10, days_offset=2)
        end = start + timedelta(hours=1)
        with self.assertRaises(RuleViolation) as ctx:
            validate_request(self.user, self.res, start, end, attendees=100)
        self.assertEqual(ctx.exception.code, "over_capacity")

    def test_too_short(self):
        start = self._next_weekday_at(10, days_offset=3)
        end = start + timedelta(minutes=10)  # less than 30 min
        with self.assertRaises(RuleViolation) as ctx:
            validate_request(self.user, self.res, start, end)
        self.assertEqual(ctx.exception.code, "too_short")

    def test_too_long(self):
        start = self._next_weekday_at(8, days_offset=4)
        end = start + timedelta(hours=5)  # more than 3h
        with self.assertRaises(RuleViolation) as ctx:
            validate_request(self.user, self.res, start, end)
        self.assertEqual(ctx.exception.code, "too_long")

    def test_beyond_booking_window(self):
        start = self._next_weekday_at(10, days_offset=60)  # >30 days ahead
        end = start + timedelta(hours=1)
        with self.assertRaises(RuleViolation) as ctx:
            validate_request(self.user, self.res, start, end)
        self.assertEqual(ctx.exception.code, "beyond_window")

    def test_blackout_blocks_booking(self):
        start = self._next_weekday_at(10, days_offset=5)
        end = start + timedelta(hours=1)
        bo = Blackout.objects.create(title="Exam Week", period=Range(start - timedelta(hours=1), end + timedelta(hours=1), bounds="[)"))
        with self.assertRaises(RuleViolation) as ctx:
            validate_request(self.user, self.res, start, end)
        self.assertEqual(ctx.exception.code, "blackout")
        bo.delete()

    def test_restricted_user_blocked(self):
        self.user.restricted_until = timezone.now() + timedelta(days=7)
        self.user.restriction_reason = "No-show"
        self.user.save()
        start = self._next_weekday_at(10, days_offset=6)
        end = start + timedelta(hours=1)
        with self.assertRaises(RuleViolation) as ctx:
            validate_request(self.user, self.res, start, end)
        self.assertEqual(ctx.exception.code, "user_restricted")
        self.user.restricted_until = None
        self.user.restriction_reason = ""
        self.user.save()

    def test_role_restriction(self):
        self.rt.allowed_roles = [Role.FACULTY]
        self.rt.save()
        start = self._next_weekday_at(10, days_offset=7)
        end = start + timedelta(hours=1)
        with self.assertRaises(RuleViolation) as ctx:
            validate_request(self.user, self.res, start, end)
        self.assertEqual(ctx.exception.code, "role_not_permitted")
        self.rt.allowed_roles = []
        self.rt.save()


# ─────────────────────────────── Quota tests ───────────────────────────────


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class QuotaEnforcementTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(code="QT", name="Quota Dept")
        cls.rt = ResourceType.objects.create(name="Room-QT", slug="room-qt")
        cls.loc = Location.objects.create(building="B-QT")
        cls.res = Resource.objects.create(
            type=cls.rt, code="RM-QT-01", name="Room QT1", location=cls.loc,
            capacity=50, department=cls.dept,
        )
        cls.user = User.objects.create_user("u_qt", password="p", role=Role.STUDENT, department=cls.dept)
        # Weekday rule, generous for testing
        AvailabilityRule.objects.create(
            resource=cls.res, name="QT Hours", weekdays=[0, 1, 2, 3, 4],
            open_time=time(0, 1), close_time=time(23, 59),
            min_duration_minutes=15, max_duration_minutes=720,
            min_lead_minutes=0, max_advance_days=60,
        )

    def test_user_hours_quota_exceeded(self):
        # 1h/week quota
        q = Quota.objects.create(department=self.dept, user_hours_per_week=1)
        # Create a 1h booking this week
        local = timezone.localtime(timezone.now())
        # Find next weekday
        target = local + timedelta(days=1)
        while target.weekday() > 4:
            target += timedelta(days=1)
        start = target.replace(hour=9, minute=0, second=0, microsecond=0)
        start = timezone.make_aware(start.replace(tzinfo=None), timezone.get_current_timezone())
        end = start + timedelta(hours=1)
        Booking.objects.create(
            resource=self.res, user=self.user, title="Existing",
            period=Range(start, end, bounds="[)"), status="confirmed", attendees=1,
        )
        BookingSlot.objects.create(resource=self.res, period=Range(start, end, bounds="[)"), kind="booking")

        # Try another 1h same week
        start2 = start + timedelta(hours=2)
        end2 = start2 + timedelta(hours=1)
        with self.assertRaises(RuleViolation) as ctx:
            validate_request(self.user, self.res, start2, end2)
        self.assertEqual(ctx.exception.code, "quota_user")
        q.delete()


# ─────────────────────────────── Policy singleton tests ───────────────────────────────


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class PolicyTests(TestCase):
    def test_policy_get_creates_singleton(self):
        Policy.objects.all().delete()
        p = Policy.get()
        self.assertEqual(p.pk, 1)
        # Calling again returns same
        p2 = Policy.get()
        self.assertEqual(p.pk, p2.pk)

    def test_default_values(self):
        p = Policy.get()
        self.assertEqual(p.grace_minutes, 15)
        self.assertEqual(p.reminder_minutes, 30)


# ─────────────────────────────── API CRUD tests ───────────────────────────────


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
)
class RulesApiTests(TestCase):
    """Test /api/availability-rules, /api/blackouts, /api/quotas, /api/policy endpoints."""

    @classmethod
    def setUpTestData(cls):
        cls.dept = Department.objects.create(code="RA", name="Rules API Dept")
        cls.rt = ResourceType.objects.create(name="Room-RA", slug="room-ra")
        cls.loc = Location.objects.create(building="B-RA")
        cls.res = Resource.objects.create(type=cls.rt, code="RM-RA-01", name="Room RA1", location=cls.loc)
        cls.admin = User.objects.create_user("adm_ra", password="p", role=Role.ADMIN, is_superuser=True)
        cls.fm = User.objects.create_user("fm_ra", password="p", role=Role.FACILITY_MANAGER)
        cls.student = User.objects.create_user("stu_ra", password="p", role=Role.STUDENT)

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(user=self.admin)

    # ── Availability rules ──
    def test_create_availability_rule(self):
        resp = self.client.post("/api/availability-rules", {
            "resource": self.res.pk,
            "name": "Test Hours",
            "weekdays": [0, 1, 2, 3, 4],
            "open_time": "08:00",
            "close_time": "20:00",
            "min_duration_minutes": 30,
            "max_duration_minutes": 120,
        }, format="json")
        self.assertEqual(resp.status_code, 201)
        self.assertEqual(resp.json()["name"], "Test Hours")

    def test_list_availability_rules(self):
        AvailabilityRule.objects.create(
            resource_type=self.rt, name="List Test",
            weekdays=[0], open_time=time(8, 0), close_time=time(18, 0),
        )
        resp = self.client.get("/api/availability-rules")
        self.assertEqual(resp.status_code, 200)
        self.assertGreaterEqual(len(resp.json()), 1)

    def test_student_cannot_create_rule(self):
        self.client.force_authenticate(user=self.student)
        resp = self.client.post("/api/availability-rules", {
            "resource_type": self.rt.pk,
            "name": "Sneaky",
            "weekdays": [0], "open_time": "08:00", "close_time": "20:00",
        }, format="json")
        self.assertIn(resp.status_code, [401, 403])

    # ── Blackouts ──
    def test_create_blackout(self):
        start = timezone.now() + timedelta(days=10)
        end = start + timedelta(days=1)
        resp = self.client.post("/api/blackouts", {
            "title": "Test Blackout",
            "start_at": start.isoformat(),
            "end_at": end.isoformat(),
        }, format="json")
        self.assertEqual(resp.status_code, 201)

    def test_list_blackouts(self):
        Blackout.objects.create(
            title="List BO",
            period=Range(timezone.now(), timezone.now() + timedelta(days=1), bounds="[)"),
        )
        resp = self.client.get("/api/blackouts")
        self.assertEqual(resp.status_code, 200)

    # ── Quotas ──
    def test_create_quota(self):
        resp = self.client.post("/api/quotas", {
            "department": self.dept.pk,
            "user_hours_per_week": 5,
            "max_active_bookings": 3,
        }, format="json")
        self.assertEqual(resp.status_code, 201)

    def test_list_quotas(self):
        resp = self.client.get("/api/quotas")
        self.assertEqual(resp.status_code, 200)

    # ── Policy ──
    def test_get_policy(self):
        resp = self.client.get("/api/policy")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("grace_minutes", resp.json())

    def test_update_policy_as_fm(self):
        self.client.force_authenticate(user=self.fm)
        resp = self.client.patch("/api/policy", {"grace_minutes": 20}, format="json")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["grace_minutes"], 20)
        # Restore
        self.client.patch("/api/policy", {"grace_minutes": 15}, format="json")

    def test_student_cannot_update_policy(self):
        self.client.force_authenticate(user=self.student)
        resp = self.client.patch("/api/policy", {"grace_minutes": 99}, format="json")
        self.assertEqual(resp.status_code, 403)
