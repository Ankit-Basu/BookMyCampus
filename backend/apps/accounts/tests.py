from datetime import timedelta
from unittest.mock import patch

from django.core.cache import cache
from django.utils import timezone
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework.throttling import ScopedRateThrottle
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Department, Role, User
from apps.accounts.permissions import IsManager, IsPolicyAdmin


class UserModelTest(APITestCase):
    def setUp(self):
        self.dept = Department.objects.create(code="CSE", name="Computer Science")
        self.student = User.objects.create_user(
            username="test.student", password="pw", role=Role.STUDENT, department=self.dept
        )
        self.faculty = User.objects.create_user(
            username="test.faculty", password="pw", role=Role.FACULTY, department=self.dept
        )
        self.custodian = User.objects.create_user(
            username="test.custodian", password="pw", role=Role.CUSTODIAN, department=self.dept
        )
        self.admin = User.objects.create_user(
            username="test.admin", password="pw", role=Role.ADMIN, department=self.dept
        )

    def test_manager_and_recurring_role_properties(self):
        self.assertFalse(self.student.is_manager)
        self.assertFalse(self.student.can_book_recurring)

        self.assertFalse(self.faculty.is_manager)
        self.assertTrue(self.faculty.can_book_recurring)

        self.assertTrue(self.custodian.is_manager)
        self.assertTrue(self.custodian.can_book_recurring)

        self.assertTrue(self.admin.is_manager)
        self.assertTrue(self.admin.can_book_recurring)

    def test_is_restricted_property(self):
        # Not restricted
        self.assertFalse(self.student.is_restricted)

        # Restricted in the past -> should be false
        self.student.restricted_until = timezone.now() - timedelta(hours=1)
        self.student.save()
        self.assertFalse(self.student.is_restricted)

        # Restricted in the future -> should be true
        self.student.restricted_until = timezone.now() + timedelta(days=7)
        self.student.save()
        self.assertTrue(self.student.is_restricted)

    def test_calendar_token_generated(self):
        self.assertIsNotNone(self.student.calendar_token)
        self.assertNotEqual(self.student.calendar_token, self.faculty.calendar_token)


class AuthEndpointsTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="alice", password="alice_password", role=Role.STUDENT, email="alice@campus.test"
        )

    def test_login_success(self):
        r = self.client.post("/api/auth/login", {"username": "alice", "password": "alice_password"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertIn("access", r.data)
        self.assertIn("refresh", r.data)
        self.assertEqual(r.data["user"]["username"], "alice")
        self.assertEqual(r.data["user"]["role"], "student")

    def test_login_invalid_password(self):
        r = self.client.post("/api/auth/login", {"username": "alice", "password": "wrong_password"}, format="json")
        self.assertEqual(r.status_code, 401)

    def test_login_nonexistent_user(self):
        r = self.client.post("/api/auth/login", {"username": "nobody", "password": "password"}, format="json")
        self.assertEqual(r.status_code, 401)

    def test_safe_refresh_token(self):
        refresh = str(RefreshToken.for_user(self.user))
        r = self.client.post("/api/auth/refresh", {"refresh": refresh}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertIn("access", r.data)

    def test_safe_refresh_with_deleted_user(self):
        temp_user = User.objects.create_user(username="temp_user", password="pw")
        refresh = str(RefreshToken.for_user(temp_user))
        temp_user.delete()

        r = self.client.post("/api/auth/refresh", {"refresh": refresh}, format="json")
        self.assertEqual(r.status_code, 401)
        self.assertEqual(r.data.get("error"), "user_not_found")

    @override_settings(DEMO_MODE=True)
    def test_demo_accounts_exposed_in_demo_mode(self):
        # Create a demo user matching the demo. pattern
        User.objects.create_user(username="demo.student", password="pw", role=Role.STUDENT)
        r = self.client.get("/api/auth/demo-accounts")
        self.assertEqual(r.status_code, 200)
        self.assertGreater(len(r.data), 0)
        self.assertTrue(any(u["username"] == "demo.student" for u in r.data))

    @override_settings(DEMO_MODE=False)
    def test_demo_accounts_hidden_outside_demo_mode(self):
        r = self.client.get("/api/auth/demo-accounts")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 0)


class MeViewTest(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="charlie", password="pw", first_name="Charlie", email="charlie@campus.test", role=Role.STUDENT
        )

    def test_me_unauthenticated_returns_401(self):
        r = self.client.get("/api/me")
        self.assertEqual(r.status_code, 401)

    def test_me_authenticated_returns_profile(self):
        self.client.force_authenticate(user=self.user)
        r = self.client.get("/api/me")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["username"], "charlie")
        self.assertEqual(r.data["first_name"], "Charlie")

    def test_me_update_allowed_fields(self):
        self.client.force_authenticate(user=self.user)
        r = self.client.patch("/api/me", {"first_name": "Charles", "phone": "9876543210"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, "Charles")
        self.assertEqual(self.user.phone, "9876543210")

    def test_me_cannot_update_role_or_username(self):
        self.client.force_authenticate(user=self.user)
        # Attempt to escalate role to admin
        self.client.patch("/api/me", {"role": Role.ADMIN, "username": "supercharlie"}, format="json")
        self.user.refresh_from_db()
        self.assertEqual(self.user.role, Role.STUDENT)
        self.assertEqual(self.user.username, "charlie")


class DepartmentAndUserManagementTest(APITestCase):
    def setUp(self):
        self.dept = Department.objects.create(code="MEC", name="Mechanical Engineering")
        self.student = User.objects.create_user(username="stu", password="pw", role=Role.STUDENT)
        self.custodian = User.objects.create_user(username="cust", password="pw", role=Role.CUSTODIAN)
        self.admin = User.objects.create_user(username="adm", password="pw", role=Role.ADMIN)

    def test_department_crud_permissions(self):
        self.client.force_authenticate(user=self.student)
        # Students can read departments
        self.assertEqual(self.client.get("/api/departments").status_code, 200)
        # Students cannot create departments
        self.assertEqual(
            self.client.post("/api/departments", {"code": "BIO", "name": "Biotech"}, format="json").status_code, 403
        )

        # Policy admin can create departments
        self.client.force_authenticate(user=self.admin)
        r = self.client.post("/api/departments", {"code": "BIO", "name": "Biotech"}, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Department.objects.filter(code="BIO").count(), 1)

    def test_user_list_permissions(self):
        # Student cannot list users
        self.client.force_authenticate(user=self.student)
        self.assertEqual(self.client.get("/api/users").status_code, 403)

        # Custodian / manager can list users
        self.client.force_authenticate(user=self.custodian)
        r = self.client.get("/api/users")
        self.assertEqual(r.status_code, 200)
        self.assertGreaterEqual(len(r.data), 3)

    def test_user_search_and_filter(self):
        self.client.force_authenticate(user=self.custodian)
        r = self.client.get("/api/users?search=adm")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.data), 1)
        self.assertEqual(r.data[0]["username"], "adm")

    def test_lift_restriction_action(self):
        # Restrict the student
        self.student.restricted_until = timezone.now() + timedelta(days=14)
        self.student.restriction_reason = "3 no-shows"
        self.student.save()
        self.assertTrue(self.student.is_restricted)

        self.client.force_authenticate(user=self.custodian)
        # Check restricted list
        restr_list = self.client.get("/api/users/restricted").data
        self.assertTrue(any(u["id"] == self.student.id for u in restr_list))

        # Lift the restriction
        r = self.client.post(f"/api/users/{self.student.id}/lift-restriction")
        self.assertEqual(r.status_code, 200)
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_restricted)
        self.assertIsNone(self.student.restricted_until)


class RegisterTest(APITestCase):
    def setUp(self):
        cache.clear()
        self.dept = Department.objects.create(code="CSE", name="Computer Science")
        self.body = {
            "registration_no": "12306448",
            "first_name": "Asha",
            "last_name": "Rao",
            "email": "Asha.Rao@lpu.in",
            "department": self.dept.id,
            "password": "fresh-pass-42",
        }

    def test_register_then_sign_in_with_the_same_credentials(self):
        r = self.client.post("/api/auth/register", self.body, format="json")
        self.assertEqual(r.status_code, 201)
        self.assertNotIn("access", r.data)
        self.assertNotIn("password", r.data)

        u = User.objects.get(username="12306448")
        self.assertEqual((u.role, u.department, u.email), (Role.STUDENT, self.dept, "asha.rao@lpu.in"))

        wrong = self.client.post("/api/auth/login", {"username": "12306448", "password": "not-the-one"}, format="json")
        self.assertEqual(wrong.status_code, 401)
        ok = self.client.post("/api/auth/login", {"username": "12306448", "password": "fresh-pass-42"}, format="json")
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.data["user"]["role"], "student")

    def test_request_cannot_choose_its_own_privileges(self):
        extra = {"role": "admin", "is_staff": True, "is_superuser": True, "username": "someone.else"}
        self.assertEqual(self.client.post("/api/auth/register", {**self.body, **extra}, format="json").status_code, 201)
        u = User.objects.get(username="12306448")
        self.assertEqual(u.role, Role.STUDENT)
        self.assertFalse(u.is_staff or u.is_superuser or u.is_manager)
        self.assertFalse(User.objects.filter(username="someone.else").exists())

    def test_registration_number_must_be_eight_digits(self):
        for bad in ("1230644", "123064480", "1230644a", "demo.admin", ""):
            r = self.client.post("/api/auth/register", {**self.body, "registration_no": bad}, format="json")
            self.assertEqual(r.status_code, 400, bad)
            self.assertIn("registration_no", r.data)

    def test_duplicates_are_refused_and_the_first_account_is_untouched(self):
        self.client.post("/api/auth/register", self.body, format="json")
        again = self.client.post("/api/auth/register", {**self.body, "email": "other@lpu.in", "password": "attacker-pass-1"}, format="json")
        self.assertEqual(again.status_code, 400)
        self.assertIn("registration_no", again.data)
        self.assertTrue(User.objects.get(username="12306448").check_password("fresh-pass-42"))

        same_mail = self.client.post("/api/auth/register", {**self.body, "registration_no": "12306449", "email": "ASHA.RAO@LPU.IN"}, format="json")
        self.assertEqual(same_mail.status_code, 400)
        self.assertIn("email", same_mail.data)

    def test_weak_passwords_are_refused(self):
        for bad in ("short", "12306448"):
            r = self.client.post("/api/auth/register", {**self.body, "password": bad}, format="json")
            self.assertEqual(r.status_code, 400, bad)
            self.assertIn("password", r.data)
        self.assertFalse(User.objects.filter(username="12306448").exists())

    def test_public_endpoints_ignore_a_stale_token(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer expired.or.garbage")
        d = self.client.get("/api/auth/departments")
        self.assertEqual(d.status_code, 200)
        self.assertEqual(d.data, [{"id": self.dept.id, "code": "CSE", "name": "Computer Science"}])
        self.assertEqual(self.client.post("/api/auth/register", self.body, format="json").status_code, 201)

    def test_scripted_sign_ups_are_throttled(self):
        with patch.object(ScopedRateThrottle, "THROTTLE_RATES", {"register": "2/hour"}):
            codes = [self.client.post("/api/auth/register", {**self.body, "registration_no": "bad"}, format="json").status_code for _ in range(3)]
        self.assertEqual(codes, [400, 400, 429])


class ProfileTest(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(username="12306448", password="old-pass-123", email="a@lpu.in")
        User.objects.create_user(username="12306449", password="x-pass-1234", email="b@lpu.in")
        self.client.force_authenticate(self.user)

    def test_change_password_then_sign_in_with_the_new_one(self):
        r = self.client.post("/api/me/password", {"current_password": "old-pass-123", "new_password": "new-pass-456"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.client.force_authenticate(None)
        self.assertEqual(self.client.post("/api/auth/login", {"username": "12306448", "password": "old-pass-123"}, format="json").status_code, 401)
        self.assertEqual(self.client.post("/api/auth/login", {"username": "12306448", "password": "new-pass-456"}, format="json").status_code, 200)

    def test_change_password_refuses_bad_input(self):
        for body, field in (
            ({"current_password": "wrong", "new_password": "new-pass-456"}, "current_password"),
            ({"current_password": "old-pass-123", "new_password": "short"}, "new_password"),
            ({"current_password": "old-pass-123", "new_password": "12306448"}, "new_password"),
        ):
            r = self.client.post("/api/me/password", body, format="json")
            self.assertEqual(r.status_code, 400, body)
            self.assertIn(field, r.data)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password("old-pass-123"))

    def test_change_password_needs_sign_in(self):
        self.client.force_authenticate(None)
        r = self.client.post("/api/me/password", {"current_password": "old-pass-123", "new_password": "new-pass-456"}, format="json")
        self.assertEqual(r.status_code, 401)

    def test_edit_profile_cannot_raise_privileges_or_steal_an_email(self):
        ok = self.client.patch("/api/me", {"phone": "9876543210", "first_name": "Asha", "email": "A@lpu.in", "role": "admin"}, format="json")
        self.assertEqual(ok.status_code, 200)
        self.user.refresh_from_db()
        self.assertEqual((self.user.phone, self.user.first_name, self.user.role), ("9876543210", "Asha", Role.STUDENT))
        taken = self.client.patch("/api/me", {"email": "B@LPU.IN"}, format="json")
        self.assertEqual(taken.status_code, 400)
        self.assertIn("email", taken.data)
