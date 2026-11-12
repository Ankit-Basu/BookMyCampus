"""HOD tools: the department overview and department notices."""
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import Department, DepartmentNotice, Role
from apps.bookings.models import Booking, NoShow
from apps.bookings.tests.factories import at, make_campus, make_user
from apps.notifications.models import Notification


class DepartmentTest(APITestCase):
    def setUp(self):
        self.cse, _, self.lab, _ = make_campus()
        self.ece = Department.objects.create(code="ECE", name="ECE")
        self.hod = make_user("hod", Role.DEPT_HEAD, self.cse)
        self.prof = make_user("prof", Role.FACULTY, self.cse)
        self.stu = make_user("12306448", Role.STUDENT, self.cse)
        self.calm = make_user("12300001", Role.STUDENT, self.cse)
        self.other = make_user("ece-stu", Role.STUDENT, self.ece)
        self.client.force_authenticate(self.hod)

    def test_overview_counts_my_department_only(self):
        b = Booking.objects.create(resource=self.lab, user=self.stu, title="Missed", period=(at(-2, 10), at(-2, 11)), status="released")
        NoShow.objects.create(booking=b, user=self.stu, resource=self.lab)
        self.stu.restricted_until = timezone.now() + timedelta(days=7)
        self.stu.save()
        Booking.objects.create(resource=self.lab, user=self.prof, title="Make-up", on_behalf_of="K22B", period=(at(1, 10), at(1, 11)), status="confirmed")

        d = self.client.get("/api/department/overview").data
        self.assertEqual(d["department"]["code"], "CSE")
        self.assertEqual((d["counts"]["faculty"], d["counts"]["students"], d["counts"]["noshows_30d"]), (2, 2, 1))
        prof = next(f for f in d["faculty"] if f["id"] == self.prof.id)
        self.assertEqual((prof["upcoming_bookings"], prof["makeups_30d"]), (1, 1))
        self.assertEqual([s["username"] for s in d["students_to_watch"]], ["12306448"])
        self.assertIsNotNone(d["students_to_watch"][0]["restricted_until"])

    def test_faculty_and_students_cannot_see_it(self):
        for u in (self.prof, self.stu):
            self.client.force_authenticate(u)
            self.assertEqual(self.client.get("/api/department/overview").status_code, 403)
            self.assertEqual(self.client.post("/api/department/notices", {"title": "x"}, format="json").status_code, 403)

    def test_hod_cannot_peek_at_another_department(self):
        self.assertEqual(self.client.get("/api/department/overview", {"department": "ECE"}).data["department"]["code"], "CSE")

    def test_notice_reaches_the_chosen_people_in_my_department(self):
        r = self.client.post("/api/department/notices", {"audience": "students", "title": "AI Lab closed Friday", "body": "GPU upgrade"}, format="json")
        self.assertEqual((r.status_code, r.data["recipients"]), (201, 2))
        got = set(Notification.objects.filter(title="CSE: AI Lab closed Friday").values_list("user__username", flat=True))
        self.assertEqual(got, {"12306448", "12300001"})
        self.assertIn("GPU upgrade", Notification.objects.filter(user=self.stu).first().body)

        everyone = self.client.post("/api/department/notices", {"title": "Department meeting"}, format="json").data
        self.assertEqual(everyone["recipients"], 4)  # prof, the lab custodian and two students: not the HOD, not ECE
        self.assertEqual([n["title"] for n in self.client.get("/api/department/notices").data], ["Department meeting", "AI Lab closed Friday"])

    def test_notice_needs_a_title_and_a_real_audience(self):
        self.assertEqual(self.client.post("/api/department/notices", {"title": " "}, format="json").data["error"], "no_title")
        self.assertEqual(self.client.post("/api/department/notices", {"title": "x", "audience": "parents"}, format="json").data["error"], "bad_audience")

    def test_ten_notices_a_day(self):
        for i in range(10):
            DepartmentNotice.objects.create(department=self.cse, author=self.hod, title=f"n{i}")
        self.assertEqual(self.client.post("/api/department/notices", {"title": "one more"}, format="json").status_code, 429)
