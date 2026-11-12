"""Faculty tools: the teaching week, the make-up class finder, and answering student requests."""
from datetime import time, timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import Role
from apps.bookings.models import Booking
from apps.bookings.tests.factories import at, make_campus, make_user
from apps.catalogue.models import Resource, ResourceType, TeacherRequest
from apps.catalogue.teaching import find_makeup_slots
from apps.notifications.models import Notification
from apps.rules.models import AvailabilityRule
from apps.timetable.services import publish


class TeachingTest(APITestCase):
    def setUp(self):
        self.dept, _, self.lab, _ = make_campus()
        self.ct = ResourceType.objects.create(name="Classroom", slug="classroom")
        AvailabilityRule.objects.create(
            resource_type=self.ct, weekdays=[0, 1, 2, 3, 4, 5, 6], open_time=time(8), close_time=time(18),
            min_duration_minutes=30, max_duration_minutes=180, min_lead_minutes=0, max_advance_days=30,
        )
        self.small = Resource.objects.create(type=self.ct, code="CR-S", name="Small Room", capacity=30, department=self.dept)
        self.big = Resource.objects.create(type=self.ct, code="CR-B", name="Big Room", capacity=80, department=self.dept)
        self.prof = make_user("prof", Role.FACULTY, self.dept)
        self.prof.first_name, self.prof.last_name = "Meera", "Iyer"
        self.prof.save()
        self.day = timezone.localdate() + timedelta(days=2)
        today = timezone.localdate()
        publish({
            "label": "Test term", "term_start": str(today - timedelta(days=7)), "term_end": str(today + timedelta(days=60)),
            "entries": [
                # The section's own class, taught by someone else, in the big room.
                {"resource_code": "CR-B", "weekday": self.day.weekday(), "start": "09:00", "end": "09:50",
                 "course_code": "CSE316", "section": "K22B", "faculty": "Dr. P. Kaur"},
                # Meera teaches another section at 11:00 in the small room.
                {"resource_code": "CR-S", "weekday": self.day.weekday(), "start": "11:00", "end": "11:50",
                 "course_code": "CSE408", "section": "K23A", "faculty": "Dr. Meera Iyer"},
            ],
        })

    def at_day(self, hour, minute=0):
        return at((self.day - timezone.localdate()).days, hour, minute)

    def test_week_lists_my_classes_and_sections(self):
        self.client.force_authenticate(self.prof)
        r = self.client.get("/api/teaching/week")
        self.assertTrue(r.data["matched_timetable"])
        self.assertEqual(r.data["my_sections"], ["K23A"])
        self.assertIn("K22B", r.data["all_sections"])
        self.assertIn("CSE408 · K23A", [i["title"] for i in r.data["items"] if i["kind"] == "class"])

    def test_students_cannot_use_teaching_tools(self):
        self.client.force_authenticate(make_user("stu", Role.STUDENT, self.dept))
        self.assertEqual(self.client.get("/api/teaching/week").status_code, 403)
        self.assertEqual(self.client.get("/api/teaching/makeup", {"section": "K22B"}).status_code, 403)

    def test_makeup_avoids_the_sections_class_and_mine_and_fits_the_size(self):
        now = self.at_day(7)
        opts = [o for o in find_makeup_slots(self.prof, "K22B", 50, 60, now=now) if timezone.localtime(o["start"]).date() == self.day]
        self.assertTrue(opts)
        for o in opts:
            s, e = o["start"], o["end"]
            self.assertFalse(s < self.at_day(9, 50) and self.at_day(9) < e, "clashes with the section's class")
            self.assertFalse(s < self.at_day(11, 50) and self.at_day(11) < e, "clashes with my class")
            self.assertEqual(o["room"]["name"], "Big Room")  # the only room that seats 60
            self.assertGreaterEqual(s, now + timedelta(hours=1))

    def test_makeup_skips_times_the_section_already_has_a_makeup(self):
        other = make_user("other", Role.FACULTY, self.dept)
        Booking.objects.create(resource=self.small, user=other, title="Earlier make-up", on_behalf_of="K22B",
                               period=(self.at_day(13), self.at_day(14)), status="confirmed")
        opts = find_makeup_slots(self.prof, "K22B", 50, 20, now=self.at_day(7))
        self.assertFalse(any(o["start"] < self.at_day(14) and self.at_day(13) < o["end"] for o in opts))

    def test_makeup_needs_a_section(self):
        self.client.force_authenticate(self.prof)
        self.assertEqual(self.client.get("/api/teaching/makeup").data["error"], "no_section")


class RequestAnswerTest(APITestCase):
    def setUp(self):
        self.dept, _, self.lab, _ = make_campus()
        self.student = make_user("12306448", Role.STUDENT, self.dept)
        self.prof = make_user("prof", Role.FACULTY, self.dept)
        self.client.force_authenticate(self.student)
        r = self.client.post(f"/api/resources/{self.lab.id}/ask-teacher",
                             {"teacher": self.prof.id, "start": at(2, 14).isoformat(), "end": at(2, 15).isoformat(), "note": "Project"},
                             format="json")
        self.req = TeacherRequest.objects.get(pk=r.data["request"])

    def test_teacher_sees_it_and_the_link_carries_the_request(self):
        self.client.force_authenticate(self.prof)
        self.assertEqual([x["id"] for x in self.client.get("/api/teacher-requests").data["incoming"]], [self.req.id])
        link = Notification.objects.get(user=self.prof).link
        self.assertIn(f"request={self.req.id}", link)
        self.assertIn("title=For+12306448", link)

    def test_declining_tells_the_student(self):
        self.client.force_authenticate(self.prof)
        r = self.client.post(f"/api/teacher-requests/{self.req.id}/decline", {"reply": "Exams that day"}, format="json")
        self.assertEqual(r.data["status"], "declined")
        n = Notification.objects.get(user=self.student)
        self.assertIn("can't book AI Lab", n.title)
        self.assertIn("Exams that day", n.body)
        again = self.client.post(f"/api/teacher-requests/{self.req.id}/decline", {}, format="json")
        self.assertEqual(again.data["error"], "already_decided")

    def test_booking_it_links_the_booking_and_tells_the_student(self):
        self.client.force_authenticate(self.prof)
        b = self.client.post("/api/bookings", {"resource": self.lab.id, "start": at(2, 14), "end": at(2, 15), "title": "For student"},
                             format="json").data
        r = self.client.post(f"/api/teacher-requests/{self.req.id}/fulfil", {"booking": b["id"]}, format="json")
        self.assertEqual((r.data["status"], r.data["booking"]), ("booked", b["id"]))
        self.assertIn("booked AI Lab for you", Notification.objects.get(user=self.student).title)

    def test_only_the_asked_teacher_can_answer(self):
        self.client.force_authenticate(make_user("prof2", Role.FACULTY, self.dept))
        self.assertEqual(self.client.post(f"/api/teacher-requests/{self.req.id}/decline", {}, format="json").status_code, 404)

    def test_cannot_fulfil_with_someone_elses_booking(self):
        other = make_user("prof3", Role.FACULTY, self.dept)
        self.client.force_authenticate(other)
        b = self.client.post("/api/bookings", {"resource": self.lab.id, "start": at(3, 14), "end": at(3, 15), "title": "Mine"},
                             format="json").data
        self.client.force_authenticate(self.prof)
        r = self.client.post(f"/api/teacher-requests/{self.req.id}/fulfil", {"booking": b["id"]}, format="json")
        self.assertEqual(r.data["error"], "bad_booking")
