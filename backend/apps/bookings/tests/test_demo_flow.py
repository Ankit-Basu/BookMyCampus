"""The story the demo tells: students and faculty book for themselves or a class, the HOD approves."""
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.db import transaction
from django.test import override_settings
from rest_framework.test import APITestCase

from apps.accounts.models import Department, Role
from apps.approvals.models import ApprovalStep, ApprovalWorkflow
from apps.bookings.models import Booking, SlotWatch
from apps.bookings.services import _insert, auto_release_sweep, set_status
from apps.catalogue.models import Resource
from apps.notifications.models import Notification

from .factories import at, make_campus, make_user


class ClassBookingTest(APITestCase):
    def setUp(self):
        self.dept, self.rtype, self.lab, _ = make_campus()
        self.student = make_user("stud", Role.STUDENT, self.dept)
        self.faculty = make_user("prof", Role.FACULTY, self.dept)
        self.hod = make_user("hod", Role.DEPT_HEAD, self.dept)
        self.dept.head = self.hod
        self.dept.save()

    def book(self, user, on_behalf_of="", lab=None):
        self.client.force_authenticate(user)
        return self.client.post("/api/bookings", {
            "resource": (lab or self.lab).id, "start": at(2, 10), "end": at(2, 11), "title": "Session", "on_behalf_of": on_behalf_of,
        }, format="json")

    def test_personal_booking_is_instant_where_no_workflow_applies(self):
        self.assertEqual(self.book(self.student).data["status"], "confirmed")

    def test_student_class_booking_needs_the_hod_who_can_then_approve_it(self):
        r = self.book(self.student, "K22CS-B")
        self.assertEqual(r.status_code, 201)
        self.assertEqual((r.data["status"], r.data["on_behalf_of"]), ("pending", "K22CS-B"))
        self.assertTrue(Notification.objects.filter(user=self.hod, kind=Notification.Kind.APPROVAL_REQUIRED).exists())

        self.client.force_authenticate(self.hod)
        self.assertEqual([b["id"] for b in self.client.get("/api/approvals/queue").data], [r.data["id"]])
        self.assertEqual(self.client.post(f"/api/bookings/{r.data['id']}/approve", {}, format="json").status_code, 200)
        self.assertEqual(Booking.objects.get(pk=r.data["id"]).status, "confirmed")

    def test_blank_class_name_is_still_a_personal_booking(self):
        self.assertEqual(self.book(self.student, "   ").data["status"], "confirmed")

    def test_faculty_class_booking_follows_the_normal_rules(self):
        self.assertEqual(self.book(self.faculty, "K22CS-B").data["status"], "confirmed")

    def test_student_cannot_approve(self):
        r = self.book(self.student, "K22CS-B")
        self.client.force_authenticate(make_user("other", Role.STUDENT, self.dept))
        self.assertEqual(self.client.post(f"/api/bookings/{r.data['id']}/approve", {}, format="json").status_code, 403)

    def test_without_any_hod_the_request_is_not_stranded(self):
        nobody = Department.objects.create(code="X", name="No head")
        lab = Resource.objects.create(type=self.rtype, code="LAB-X", name="Lab X", capacity=10, department=nobody)
        student = make_user("lonely", Role.STUDENT, nobody)
        manager = make_user("mgr", Role.FACILITY_MANAGER, nobody)
        r = self.book(student, "K22CS-B", lab)
        self.client.force_authenticate(manager)
        self.assertEqual([b["id"] for b in self.client.get("/api/approvals/queue").data], [r.data["id"]])


class HodRoutingTest(APITestCase):
    def setUp(self):
        self.cse, self.rtype, self.lab, _ = make_campus()
        self.ece = Department.objects.create(code="ECE", name="ECE")
        self.mec = Department.objects.create(code="MEC", name="MEC")
        self.ece_lab = Resource.objects.create(type=self.rtype, code="LAB-E", name="ECE Lab", capacity=10, department=self.ece)
        self.student = make_user("stud", Role.STUDENT, self.cse)
        self.cse_hod = make_user("hcse", Role.DEPT_HEAD, self.cse)
        self.ece_hod = make_user("hece", Role.DEPT_HEAD, self.ece)
        self.mec_hod = make_user("hmec", Role.DEPT_HEAD, self.mec)
        wf = ApprovalWorkflow.objects.create(name="Labs", resource_type=self.rtype, requester_roles=[Role.STUDENT])
        ApprovalStep.objects.create(workflow=wf, order=1, name="HOD approval", approver_role=Role.DEPT_HEAD)
        self.client.force_authenticate(self.student)
        self.booking = self.client.post("/api/bookings", {
            "resource": self.ece_lab.id, "start": at(2, 10), "end": at(2, 11), "title": "Across departments",
        }, format="json").data["id"]

    def queue(self, user):
        self.client.force_authenticate(user)
        return [b["id"] for b in self.client.get("/api/approvals/queue").data]

    def test_requester_hod_and_owner_hod_both_see_it_and_no_one_else(self):
        self.assertEqual(self.queue(self.cse_hod), [self.booking])
        self.assertEqual(self.queue(self.ece_hod), [self.booking])
        self.assertEqual(self.queue(self.mec_hod), [])

    def test_unrelated_hod_cannot_approve_but_the_requesters_can(self):
        self.client.force_authenticate(self.mec_hod)
        self.assertEqual(self.client.post(f"/api/bookings/{self.booking}/approve", {}, format="json").status_code, 403)
        self.client.force_authenticate(self.cse_hod)
        self.assertEqual(self.client.post(f"/api/bookings/{self.booking}/approve", {}, format="json").status_code, 200)


class WaitlistTest(APITestCase):
    def setUp(self):
        self.dept, self.rtype, self.lab, _ = make_campus()
        self.holder = make_user("holder", Role.FACULTY, self.dept)
        self.waiter = make_user("waiter", Role.STUDENT, self.dept)
        self.client.force_authenticate(self.holder)
        self.start, self.end = at(2, 10), at(2, 11)
        self.booking = self.client.post("/api/bookings", {"resource": self.lab.id, "start": self.start, "end": self.end, "title": "Held"}, format="json").data["id"]
        self.body = {"start": self.start, "end": self.end}

    def watch(self, user, body=None):
        self.client.force_authenticate(user)
        return self.client.post(f"/api/resources/{self.lab.id}/watch", body or self.body, format="json")

    def freed_notes(self, user):
        return Notification.objects.filter(user=user, title__startswith="A slot just opened")

    def test_cancelling_tells_the_waitlist_exactly_once(self):
        self.assertEqual(self.watch(self.waiter).status_code, 201)
        self.assertEqual(self.watch(self.waiter).status_code, 201)  # repeat is harmless
        self.assertEqual(SlotWatch.objects.count(), 1)

        self.client.force_authenticate(self.holder)
        self.assertEqual(self.client.post(f"/api/bookings/{self.booking}/cancel", {}, format="json").status_code, 200)
        self.assertEqual(self.freed_notes(self.waiter).count(), 1)
        self.assertEqual(self.freed_notes(self.waiter).first().link, f"/resources/{self.lab.id}")
        self.assertIsNotNone(SlotWatch.objects.get().notified_at)

    def test_rejection_also_frees_the_slot_for_the_waitlist(self):
        self.watch(self.waiter)
        set_status(Booking.objects.get(pk=self.booking), Booking.Status.REJECTED, "no")
        self.assertEqual(self.freed_notes(self.waiter).count(), 1)

    def test_only_overlapping_watches_hear_about_it(self):
        self.client.force_authenticate(self.holder)
        later = self.client.post("/api/bookings", {"resource": self.lab.id, "start": at(2, 14), "end": at(2, 15), "title": "Later"}, format="json").data["id"]
        self.watch(self.waiter, {"start": at(2, 14), "end": at(2, 15)})
        self.client.force_authenticate(self.holder)
        self.client.post(f"/api/bookings/{self.booking}/cancel", {}, format="json")
        self.assertEqual(self.freed_notes(self.waiter).count(), 0)
        self.client.post(f"/api/bookings/{later}/cancel", {}, format="json")
        self.assertEqual(self.freed_notes(self.waiter).count(), 1)

    def test_refuses_what_there_is_nothing_to_wait_for(self):
        self.assertEqual(self.watch(self.holder).status_code, 400)  # your own booking
        self.assertEqual(self.watch(self.waiter, {"start": at(3, 10), "end": at(3, 11)}).status_code, 400)  # free
        self.assertEqual(self.watch(self.waiter, {"start": at(-2, 10), "end": at(-2, 11)}).status_code, 400)  # past
        self.assertEqual(self.watch(self.waiter, {"start": self.end, "end": self.start}).status_code, 400)  # backwards
        self.assertEqual(self.watch(self.waiter, {"start": "junk", "end": "junk"}).status_code, 400)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post(f"/api/resources/{self.lab.id}/watch", self.body, format="json").status_code, 401)


class AlternativesAndInsightsTest(APITestCase):
    def setUp(self):
        self.dept, self.rtype, self.lab, _ = make_campus()
        self.free_lab = Resource.objects.create(type=self.rtype, code="LAB-2", name="Free Lab", capacity=40, department=self.dept)
        self.busy_lab = Resource.objects.create(type=self.rtype, code="LAB-3", name="Busy Lab", capacity=40, department=self.dept)
        self.down_lab = Resource.objects.create(type=self.rtype, code="LAB-4", name="Down Lab", capacity=40, status=Resource.Status.DOWN)
        self.student = make_user("stud", Role.STUDENT, self.dept)
        self.client.force_authenticate(self.student)
        for r in (self.lab, self.busy_lab):
            self.client.post("/api/bookings", {"resource": r.id, "start": at(2, 10), "end": at(2, 11), "title": "Held"}, format="json")

    def test_only_rooms_free_at_that_time_are_offered_with_the_next_free_time(self):
        r = self.client.get(f"/api/resources/{self.lab.id}/alternatives", {"start": at(2, 10).isoformat(), "end": at(2, 11).isoformat()})
        self.assertEqual(r.status_code, 200)
        self.assertEqual([x["name"] for x in r.data["rooms"]], ["Free Lab"])
        self.assertIsNotNone(r.data["next_free"])
        self.assertGreaterEqual(r.data["next_free"], at(2, 10))

    def test_rooms_the_rules_would_refuse_are_not_offered(self):
        self.rtype.allowed_roles = [Role.FACULTY]
        self.rtype.save()
        r = self.client.get(f"/api/resources/{self.lab.id}/alternatives", {"start": at(2, 10).isoformat(), "end": at(2, 11).isoformat()})
        self.assertEqual(r.data["rooms"], [])

    def test_bad_times_are_refused(self):
        self.assertEqual(self.client.get(f"/api/resources/{self.lab.id}/alternatives", {"start": "x", "end": "y"}).status_code, 400)

    def test_insights_cover_opening_hours_and_pick_a_quiet_one(self):
        empty = self.client.get(f"/api/resources/{self.free_lab.id}/insights").data
        self.assertEqual((empty["hours"][0]["hour"], empty["hours"][-1]["hour"], empty["quietest"]), (6, 22, None))
        with transaction.atomic():
            _insert(self.student, self.free_lab, at(-3, 10), at(-3, 12), title="Past")
        data = self.client.get(f"/api/resources/{self.free_lab.id}/insights").data
        busy = {h["hour"]: h["busy"] for h in data["hours"]}
        self.assertGreater(busy[10], 0)
        self.assertGreater(busy[11], 0)
        self.assertEqual(busy[12], 0)
        self.assertNotIn(data["quietest"], (10, 11))


class DemoPersonaTest(APITestCase):
    @override_settings(DEMO_MODE=True)
    def test_login_offers_exactly_student_faculty_and_hod(self):
        for name, role in (("student", Role.STUDENT), ("faculty", Role.FACULTY), ("head", Role.DEPT_HEAD), ("manager", Role.FACILITY_MANAGER), ("admin", Role.ADMIN), ("custodian", Role.CUSTODIAN)):
            make_user(f"demo.{name}", role)
        r = self.client.get("/api/auth/demo-accounts")
        self.assertEqual([u["role"] for u in r.data], ["student", "faculty", "dept_head"])

    def _missed(self, user, lab):
        with transaction.atomic():
            b = _insert(user, lab, at(-1, 10), at(-1, 11), title="Missed")
        auto_release_sweep()
        return Booking.objects.get(pk=b.pk)

    @override_settings(DEMO_MODE=True)
    def test_a_persona_stays_bookable_when_nobody_checks_in_for_it(self):
        _, _, lab, _ = make_campus()
        persona = make_user("demo.student", Role.STUDENT)
        self.assertEqual(self._missed(persona, lab).status, "released")
        persona.refresh_from_db()
        self.assertEqual(persona.noshows.count(), 0)
        self.assertFalse(persona.is_restricted)

    @override_settings(DEMO_MODE=False)
    def test_outside_demo_mode_even_demo_named_accounts_get_strikes(self):
        _, _, lab, _ = make_campus()
        persona = make_user("demo.student", Role.STUDENT)
        self._missed(persona, lab)
        self.assertEqual(persona.noshows.count(), 1)

    @override_settings(DEMO_MODE=True)
    def test_real_students_still_get_strikes(self):
        _, _, lab, _ = make_campus()
        real = make_user("12306448", Role.STUDENT)
        self._missed(real, lab)
        self.assertEqual(real.noshows.count(), 1)


class SchedulerTest(APITestCase):
    def test_a_failed_sweep_does_not_end_the_loop(self):
        ok = {"released": 0, "completed": 0, "reminders": 0}
        with patch("apps.bookings.management.commands.run_scheduler.sweep_once", side_effect=[RuntimeError("database went away"), ok]) as sweep, \
                patch("apps.bookings.management.commands.run_scheduler.time.sleep", side_effect=[None, KeyboardInterrupt]), \
                patch("apps.bookings.management.commands.run_scheduler.close_old_connections"):
            with self.assertRaises(KeyboardInterrupt):
                call_command("run_scheduler", stderr=StringIO(), stdout=StringIO())
        self.assertEqual(sweep.call_count, 2)
