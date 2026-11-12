"""Study spots and asking a teacher: what students get beyond booking."""
from django.core.cache import cache
from rest_framework.test import APITestCase

from apps.accounts.models import Role
from apps.bookings.services import _insert
from apps.bookings.tests.factories import at, make_campus, make_user
from apps.catalogue.models import Resource
from apps.catalogue.student import study_spots_at
from apps.notifications.models import Notification


class StudySpotsTest(APITestCase):
    def setUp(self):
        self.dept, self.rtype, self.lab, _ = make_campus()
        self.busy = Resource.objects.create(type=self.rtype, code="LAB-2", name="Busy Lab", capacity=30, department=self.dept)
        self.down = Resource.objects.create(type=self.rtype, code="LAB-3", name="Down Lab", capacity=30, status=Resource.Status.DOWN)
        self.faculty = make_user("prof", Role.FACULTY, self.dept)
        _insert(self.faculty, self.busy, at(2, 10), at(2, 12), title="Practical")
        _insert(self.faculty, self.lab, at(2, 13), at(2, 14), title="Later")

    def test_lists_rooms_with_nothing_on_and_how_long_they_stay_free(self):
        free, soon = study_spots_at(at(2, 11))
        self.assertEqual([(s["name"], s["free_until"]) for s in free], [("AI Lab", at(2, 13))])
        self.assertEqual(free[0]["minutes"], 120)
        self.assertEqual([(s["name"], s["free_from"]) for s in soon], [("Busy Lab", at(2, 12))])

    def test_closed_rooms_are_not_offered(self):
        self.assertEqual(study_spots_at(at(2, 23, 30)), ([], []))

    def test_short_gaps_are_not_worth_walking_to(self):
        free, _ = study_spots_at(at(2, 12, 50))
        self.assertNotIn("AI Lab", [s["name"] for s in free])

    def test_endpoint_needs_sign_in_and_accepts_a_time(self):
        self.assertEqual(self.client.get("/api/study-spots").status_code, 401)
        self.client.force_authenticate(make_user("stu", Role.STUDENT, self.dept))
        r = self.client.get("/api/study-spots", {"at": at(2, 11).isoformat()})
        self.assertEqual([s["name"] for s in r.data["free"]], ["AI Lab"])


class AskTeacherTest(APITestCase):
    def setUp(self):
        cache.clear()
        self.dept, self.rtype, self.lab, _ = make_campus()
        self.student = make_user("12306448", Role.STUDENT, self.dept)
        self.student.first_name = "Riya"
        self.student.save()
        self.teacher = make_user("prof", Role.FACULTY, self.dept)
        self.client.force_authenticate(self.student)

    def ask(self, **over):
        body = {"teacher": self.teacher.id, "start": at(2, 14).isoformat(), "end": at(2, 15).isoformat(), "note": "Group project", **over}
        return self.client.post(f"/api/resources/{self.lab.id}/ask-teacher", body, format="json")

    def test_teacher_gets_a_link_with_the_slot_filled_in(self):
        r = self.ask()
        self.assertEqual(r.status_code, 201)
        n = Notification.objects.get(user=self.teacher)
        self.assertIn("Riya asks you to book AI Lab", n.title)
        self.assertIn("Group project", n.body)
        self.assertTrue(n.link.startswith(f"/resources/{self.lab.id}?start="))
        self.assertIn("&end=", n.link)

    def test_teacher_list_puts_own_department_first(self):
        from apps.accounts.models import Department

        other = Department.objects.create(code="ECE", name="ECE")
        make_user("aaa", Role.FACULTY, other)
        names = [(t["name"], t["same_department"]) for t in self.client.get("/api/teachers").data]
        self.assertEqual(names[0], ("prof", True))
        self.assertNotIn(("12306448", False), names)

    def test_only_teachers_can_be_asked(self):
        other_student = make_user("friend", Role.STUDENT, self.dept)
        self.assertEqual(self.ask(teacher=other_student.id).data["error"], "bad_teacher")

    def test_bad_times_are_refused(self):
        self.assertEqual(self.ask(start=at(-1, 10).isoformat(), end=at(-1, 11).isoformat()).data["error"], "slot_passed")
        self.assertEqual(self.ask(end=at(2, 13).isoformat()).data["error"], "invalid_period")
        self.assertEqual(self.ask(end=at(2, 20).isoformat()).data["error"], "too_long")

    def test_cannot_ask_for_a_time_the_room_is_taken(self):
        _insert(self.teacher, self.lab, at(2, 14), at(2, 15), title="Practical")
        r = self.ask()
        self.assertEqual((r.status_code, r.data["error"]), (409, "slot_taken"))
        self.assertIn("has a booking then", r.data["message"])

    def test_ten_requests_a_day(self):
        for _ in range(10):
            self.assertEqual(self.ask().status_code, 201)
        self.assertEqual(self.ask().status_code, 429)
