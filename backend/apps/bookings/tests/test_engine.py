from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import Role
from apps.approvals.models import ApprovalStep, ApprovalWorkflow
from apps.approvals.services import decide
from apps.bookings.exceptions import BookingError, RuleViolation, SlotConflict
from apps.bookings.models import Booking, BookingSlot, NoShow
from apps.bookings.services import (
    _insert,
    auto_release_sweep,
    cancel,
    check_in,
    check_out,
    create_booking,
    create_recurring,
    tsrange,
)
from apps.maintenance.services import schedule
from apps.rules.models import Blackout, Policy, Quota
from apps.rules.services import availability
from apps.timetable.services import publish

from .factories import at, make_campus, make_user


class ConstraintTest(TestCase):
    def setUp(self):
        self.dept, self.rtype, self.lab, self.custodian = make_campus()
        self.alice = make_user("alice", dept=self.dept)
        self.bob = make_user("bob", dept=self.dept)

    def test_database_itself_refuses_overlap(self):
        """Bypass every line of Python: a raw second insert is still rejected by PostgreSQL."""
        Booking.objects.create(resource=self.lab, user=self.alice, title="a", period=tsrange(at(1, 10), at(1, 12)))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Booking.objects.create(resource=self.lab, user=self.bob, title="b", period=tsrange(at(1, 11), at(1, 13)))

    def test_adjacent_bookings_allowed(self):
        create_booking(self.alice, self.lab, at(1, 10), at(1, 11), title="a")
        create_booking(self.bob, self.lab, at(1, 11), at(1, 12), title="b")  # half-open [) ranges touch, don't overlap
        self.assertEqual(Booking.objects.count(), 2)

    def test_conflict_is_409_with_reason(self):
        create_booking(self.alice, self.lab, at(1, 10), at(1, 12), title="a")
        with self.assertRaises(SlotConflict) as ctx:
            create_booking(self.bob, self.lab, at(1, 11), at(1, 13), title="b")
        self.assertEqual(ctx.exception.http_status, 409)
        self.assertEqual(ctx.exception.details["kind"], "booking")

    def test_cancel_frees_the_slot(self):
        b = create_booking(self.alice, self.lab, at(1, 10), at(1, 12), title="a")
        cancel(b, self.alice)
        create_booking(self.bob, self.lab, at(1, 10), at(1, 12), title="b")


class TimetableTest(TestCase):
    def setUp(self):
        self.dept, self.rtype, self.lab, _ = make_campus()
        self.alice = make_user("alice", dept=self.dept)
        tomorrow = timezone.localdate() + timedelta(days=1)
        publish({
            "label": "t1", "term_start": (tomorrow - timedelta(days=7)).isoformat(),
            "term_end": (tomorrow + timedelta(days=30)).isoformat(),
            "entries": [{"resource_code": "LAB-1", "weekday": tomorrow.weekday(), "start": "10:00", "end": "11:00", "course_code": "CSE326"}],
        })

    def test_timetabled_slot_never_offered(self):
        day = timezone.localdate() + timedelta(days=1)
        data = availability(self.lab, day, day + timedelta(days=1))
        lecture = (at(1, 10), at(1, 11))
        for s in data["free"]:
            self.assertFalse(s["start"] < lecture[1] and s["end"] > lecture[0], f"offered {s} during lecture")
        self.assertTrue(any(b["kind"] == "timetable" for b in data["busy"]))

    def test_cannot_book_over_lecture(self):
        with self.assertRaises(SlotConflict) as ctx:
            create_booking(self.alice, self.lab, at(1, 10, 30), at(1, 11, 30), title="x")
        self.assertEqual(ctx.exception.details["kind"], "timetable")

    def test_republish_displaces_and_is_idempotent(self):
        b = create_booking(self.alice, self.lab, at(1, 14), at(1, 15), title="mine")
        tomorrow = timezone.localdate() + timedelta(days=1)
        payload = {
            "label": "t2", "term_start": (tomorrow - timedelta(days=7)).isoformat(),
            "term_end": (tomorrow + timedelta(days=30)).isoformat(),
            "entries": [{"resource_code": "LAB-1", "weekday": tomorrow.weekday(), "start": "14:00", "end": "15:00", "course_code": "CSE408"}],
        }
        v, changed = publish(payload)
        self.assertTrue(changed)
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.Status.DISPLACED)
        self.assertEqual(v.displaced_bookings, 1)
        # old 10:00 lecture slot is gone, new one is in
        create_booking(self.alice, self.lab, at(1, 10), at(1, 11), title="now free")
        _, changed_again = publish(payload)
        self.assertFalse(changed_again)


class RulesTest(TestCase):
    def setUp(self):
        self.dept, self.rtype, self.lab, _ = make_campus()
        self.alice = make_user("alice", dept=self.dept)

    def test_outside_hours(self):
        with self.assertRaises(RuleViolation) as ctx:
            create_booking(self.alice, self.lab, at(1, 23, 30), at(2, 0, 30), title="x")
        self.assertEqual(ctx.exception.code, "outside_hours")

    def test_too_long(self):
        with self.assertRaises(RuleViolation) as ctx:
            create_booking(self.alice, self.lab, at(1, 8), at(1, 13), title="x")
        self.assertEqual(ctx.exception.code, "too_long")

    def test_blackout(self):
        Blackout.objects.create(title="Exams", period=tsrange(at(1, 0), at(2, 0)))
        with self.assertRaises(RuleViolation) as ctx:
            create_booking(self.alice, self.lab, at(1, 10), at(1, 11), title="x")
        self.assertEqual(ctx.exception.code, "blackout")

    def test_role_restriction(self):
        self.rtype.allowed_roles = [Role.FACULTY]
        self.rtype.save()
        with self.assertRaises(RuleViolation) as ctx:
            create_booking(self.alice, self.lab, at(1, 10), at(1, 11), title="x")
        self.assertEqual(ctx.exception.code, "role_not_permitted")

    def test_user_weekly_quota(self):
        Quota.objects.create(role=Role.STUDENT, user_hours_per_week=2)
        day = 7 + (0 - timezone.localdate().weekday()) % 7  # a Monday next week or later — same ISO week
        create_booking(self.alice, self.lab, at(day, 9), at(day, 10), title="1")
        create_booking(self.alice, self.lab, at(day, 10), at(day, 11), title="2")
        with self.assertRaises(RuleViolation) as ctx:
            create_booking(self.alice, self.lab, at(day, 12), at(day, 13), title="3")
        self.assertEqual(ctx.exception.code, "quota_user")

    def test_department_quota(self):
        Quota.objects.create(department=self.dept, department_hours_per_week=1)
        bob = make_user("bob", dept=self.dept)
        day = 7 + (0 - timezone.localdate().weekday()) % 7
        create_booking(self.alice, self.lab, at(day, 9), at(day, 10), title="1")
        with self.assertRaises(RuleViolation) as ctx:
            create_booking(bob, self.lab, at(day, 12), at(day, 13), title="2")
        self.assertEqual(ctx.exception.code, "quota_department")


class RecurringTest(TestCase):
    def setUp(self):
        self.dept, self.rtype, self.lab, _ = make_campus()
        self.prof = make_user("prof", Role.FACULTY, self.dept)
        self.other = make_user("other", dept=self.dept)
        # Someone already holds week 3 of the series.
        create_booking(self.other, self.lab, at(1 + 14, 16), at(1 + 14, 17), title="in the way")

    def test_mid_series_conflict_skipped(self):
        rule, created, skipped = create_recurring(
            self.prof, self.lab, at(1, 16), at(1, 17), title="Tutorial", freq="weekly", count=5, conflict_policy="skip"
        )
        self.assertEqual(len(created), 4)
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0]["index"], 2)
        self.assertEqual(skipped[0]["code"], "slot_conflict")

    def test_all_or_nothing_rolls_back(self):
        with self.assertRaises(BookingError) as ctx:
            create_recurring(
                self.prof, self.lab, at(1, 16), at(1, 17), title="Tutorial", freq="weekly", count=5, conflict_policy="abort"
            )
        self.assertEqual(ctx.exception.code, "series_conflict")
        self.assertEqual(Booking.objects.filter(user=self.prof).count(), 0)
        self.assertEqual(BookingSlot.objects.filter(booking__user=self.prof).count(), 0)

    def test_students_cannot_recur(self):
        with self.assertRaises(RuleViolation):
            create_recurring(self.other, self.lab, at(1, 9), at(1, 10), title="x", count=3)


class CheckInAndReleaseTest(TestCase):
    def setUp(self):
        self.dept, self.rtype, self.lab, self.custodian = make_campus()
        self.alice = make_user("alice", dept=self.dept)
        self.policy = Policy.get()
        self.start = timezone.now().replace(second=0, microsecond=0) + timedelta(hours=1)
        self.b = _insert(self.alice, self.lab, self.start, self.start + timedelta(hours=1), title="session")

    def test_auto_release_fires_after_grace_only(self):
        g = self.policy.grace_minutes
        self.assertEqual(auto_release_sweep(now=self.start + timedelta(minutes=g - 1)), 0)
        self.b.refresh_from_db()
        self.assertEqual(self.b.status, Booking.Status.CONFIRMED)
        self.assertEqual(auto_release_sweep(now=self.start + timedelta(minutes=g + 1)), 1)
        self.b.refresh_from_db()
        self.assertEqual(self.b.status, Booking.Status.RELEASED)
        self.assertTrue(NoShow.objects.filter(booking=self.b).exists())
        self.assertFalse(BookingSlot.objects.filter(booking=self.b).exists())  # slot handed back

    def test_checkin_with_resource_qr_then_checkout_frees_rest(self):
        check_in(self.b, self.alice, str(self.lab.checkin_token), now=self.start + timedelta(minutes=2))
        self.assertEqual(auto_release_sweep(now=self.start + timedelta(minutes=60)), 0)
        check_out(self.b, self.alice, now=self.start + timedelta(minutes=20))
        self.b.refresh_from_db()
        self.assertEqual(self.b.status, Booking.Status.COMPLETED)
        self.assertEqual(self.b.end, self.start + timedelta(minutes=20))

    def test_checkin_window(self):
        with self.assertRaises(BookingError) as ctx:
            check_in(self.b, self.alice, str(self.lab.checkin_token), now=self.start - timedelta(minutes=30))
        self.assertEqual(ctx.exception.code, "too_early")
        with self.assertRaises(BookingError) as ctx:
            check_in(self.b, self.alice, str(self.lab.checkin_token), now=self.start + timedelta(minutes=40))
        self.assertEqual(ctx.exception.code, "too_late")

    def test_wrong_qr(self):
        with self.assertRaises(BookingError) as ctx:
            check_in(self.b, self.alice, "not-a-token", now=self.start)
        self.assertEqual(ctx.exception.code, "bad_token")

    def test_custodian_scans_pass(self):
        check_in(self.b, self.custodian, str(self.b.qr_token), now=self.start)
        self.b.refresh_from_db()
        self.assertEqual(self.b.checkin.method, "booking_qr")

    def test_progressive_restriction(self):
        for i in range(self.policy.strike_level1):
            s = self.start + timedelta(days=i + 1)
            b = _insert(self.alice, self.lab, s, s + timedelta(hours=1), title=f"miss {i}")
            auto_release_sweep(now=s + timedelta(minutes=self.policy.grace_minutes + 1))
            b.refresh_from_db()
            self.assertEqual(b.status, Booking.Status.RELEASED)
        self.alice.refresh_from_db()
        self.assertTrue(self.alice.is_restricted)
        with self.assertRaises(RuleViolation) as ctx:
            create_booking(self.alice, self.lab, at(5, 9), at(5, 10), title="blocked")
        self.assertEqual(ctx.exception.code, "user_restricted")


class ApprovalTest(TestCase):
    def setUp(self):
        self.dept, self.rtype, self.lab, self.custodian = make_campus()
        self.head = make_user("head", Role.DEPT_HEAD, self.dept)
        self.dept.head = self.head
        self.dept.save()
        wf = ApprovalWorkflow.objects.create(name="Two step", resource_type=self.rtype, requester_roles=[Role.STUDENT])
        ApprovalStep.objects.create(workflow=wf, order=1, name="Custodian", approver_role=Role.CUSTODIAN)
        ApprovalStep.objects.create(workflow=wf, order=2, name="HoD", approver_role=Role.DEPT_HEAD)
        self.alice = make_user("alice", dept=self.dept)
        self.prof = make_user("prof", Role.FACULTY, self.dept)

    def test_chain_in_order(self):
        b = create_booking(self.alice, self.lab, at(1, 10), at(1, 11), title="x")
        self.assertEqual(b.status, Booking.Status.PENDING)
        with self.assertRaises(BookingError):
            decide(b, self.head, True)  # HoD can't jump the queue
        decide(b, self.custodian, True)
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.Status.PENDING)
        decide(b, self.head, True)
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.Status.CONFIRMED)

    def test_pending_holds_slot_and_reject_frees_it(self):
        b = create_booking(self.alice, self.lab, at(1, 10), at(1, 11), title="x")
        with self.assertRaises(SlotConflict):
            create_booking(self.prof, self.lab, at(1, 10), at(1, 11), title="y")
        decide(b, self.custodian, False, "Lab reserved for exam prep")
        create_booking(self.prof, self.lab, at(1, 10), at(1, 11), title="y")

    def test_workflow_is_per_role(self):
        b = create_booking(self.prof, self.lab, at(1, 12), at(1, 13), title="faculty")
        self.assertEqual(b.status, Booking.Status.CONFIRMED)


class MaintenanceTest(TestCase):
    def setUp(self):
        self.dept, self.rtype, self.lab, self.custodian = make_campus()
        self.alice = make_user("alice", dept=self.dept)

    def test_maintenance_displaces_and_blocks(self):
        b = create_booking(self.alice, self.lab, at(1, 10), at(1, 11), title="x")
        w = schedule(self.lab, at(1, 9), at(1, 12), title="Service")
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.Status.DISPLACED)
        self.assertEqual(w.displaced_bookings, 1)
        with self.assertRaises(SlotConflict) as ctx:
            create_booking(self.alice, self.lab, at(1, 11), at(1, 12), title="y")
        self.assertEqual(ctx.exception.details["kind"], "maintenance")
