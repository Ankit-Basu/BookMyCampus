from datetime import timedelta
from django.utils import timezone
from django.test import override_settings
from rest_framework.test import APITestCase
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

    @override_settings(DEBUG=True)
    def test_demo_accounts_exposed_in_debug(self):
        # Create a demo user matching the demo. pattern
        User.objects.create_user(username="demo.student", password="pw", role=Role.STUDENT)
        r = self.client.get("/api/auth/demo-accounts")
        self.assertEqual(r.status_code, 200)
        self.assertGreater(len(r.data), 0)
        self.assertTrue(any(u["username"] == "demo.student" for u in r.data))

    @override_settings(DEBUG=False)
    def test_demo_accounts_hidden_in_production(self):
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
