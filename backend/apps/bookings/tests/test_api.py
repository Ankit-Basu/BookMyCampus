"""
End-to-end API checks: every endpoint group the frontend uses, exercised through HTTP with real
permissions. These complement the engine tests, which call services directly.
"""
from datetime import timedelta

from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import Role
from apps.approvals.models import ApprovalStep, ApprovalWorkflow
from apps.bookings.models import Booking, NoShow
from apps.bookings.services import _insert
from apps.consumables.models import Consumable
from apps.notifications.models import Notification

from .factories import at, make_campus, make_user


@override_settings(TIMETABLE_WEBHOOK_TOKEN="p13-secret")
class ApiTest(APITestCase):
    def setUp(self):
        self.dept, self.rtype, self.lab, self.custodian = make_campus()
        self.student = make_user("stud", Role.STUDENT, self.dept)
        self.prof = make_user("prof", Role.FACULTY, self.dept)
        self.manager = make_user("mgr", Role.FACILITY_MANAGER, self.dept)

    def as_(self, user):
        self.client.force_authenticate(user)

    # ------------------------------------------------------------- auth
    def test_login_returns_tokens_and_profile(self):
        r = self.client.post("/api/auth/login", {"username": "stud", "password": "x"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertIn("access", r.data)
        self.assertEqual(r.data["user"]["role"], "student")
        bad = self.client.post("/api/auth/login", {"username": "stud", "password": "nope"}, format="json")
        self.assertEqual(bad.status_code, 401)

    def test_refresh_for_deleted_user_is_401_not_500(self):
        r = self.client.post("/api/auth/login", {"username": "stud", "password": "x"}, format="json")
        refresh = r.data["refresh"]
        self.student.delete()
        r2 = self.client.post("/api/auth/refresh", {"refresh": refresh}, format="json")
        self.assertEqual(r2.status_code, 401)

    def test_anonymous_is_rejected(self):
        self.assertEqual(self.client.get("/api/resources").status_code, 401)

    def test_public_stats_open(self):
        r = self.client.get("/api/public/stats")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data["double_bookings"], 0)

    # ------------------------------------------------------------- catalogue
    def test_catalogue_search_facets_availability_qr(self):
        self.as_(self.student)
        r = self.client.get("/api/resources", {"q": "AI"})
        self.assertEqual([x["code"] for x in r.data], ["LAB-1"])
        self.assertEqual(self.client.get("/api/resources/facets").status_code, 200)
        day = (timezone.localdate() + timedelta(days=1)).isoformat()
        av = self.client.get(f"/api/resources/{self.lab.id}/availability", {"from": day})
        self.assertEqual(av.status_code, 200)
        self.assertTrue(av.data["free"])
        qr = self.client.get(f"/api/resources/{self.lab.id}/qr")
        self.assertEqual(qr["Content-Type"], "image/svg+xml")

    def test_free_now_filter_excludes_busy(self):
        _insert(self.prof, self.lab, at(1, 10), at(1, 11), title="x")
        self.as_(self.student)
        r = self.client.get("/api/resources", {"free_from": at(1, 10).isoformat(), "free_to": at(1, 11).isoformat()})
        self.assertEqual(r.data, [])

    def test_students_cannot_edit_catalogue(self):
        self.as_(self.student)
        r = self.client.patch(f"/api/resources/{self.lab.id}", {"name": "Hacked"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_bulk_import(self):
        self.as_(self.manager)
        csv = "code,name,type,department,building,capacity,features\nLAB-9,New Lab,Laboratory,CSE,Block 34,20,GPU|AC\n"
        r = self.client.post("/api/resources/bulk-import", {"csv": csv}, format="json")
        self.assertEqual((r.data["created"], r.data["errors"]), (1, []))

    # ------------------------------------------------------------- booking lifecycle
    def test_book_conflict_rule_and_cancel(self):
        self.as_(self.student)
        body = {"resource": self.lab.id, "start": at(1, 10).isoformat(), "end": at(1, 11).isoformat(), "title": "Study"}
        r = self.client.post("/api/bookings", body, format="json")
        self.assertEqual(r.status_code, 201, r.data)
        bid = r.data["id"]
        self.as_(self.prof)
        clash = self.client.post("/api/bookings", body, format="json")
        self.assertEqual((clash.status_code, clash.data["error"]), (409, "slot_conflict"))
        late = dict(body, start=at(1, 22, 30).isoformat(), end=at(1, 23, 30).isoformat())
        rule = self.client.post("/api/bookings", late, format="json")
        self.assertEqual((rule.status_code, rule.data["error"]), (422, "outside_hours"))
        # only the owner (or a manager) may cancel
        self.assertEqual(self.client.post(f"/api/bookings/{bid}/cancel").status_code, 404)
        self.as_(self.student)
        self.assertEqual(self.client.post(f"/api/bookings/{bid}/cancel").data["status"], "cancelled")
        self.assertEqual(self.client.get(f"/api/bookings/{bid}/ics").status_code, 200)

    def test_recurring_endpoint(self):
        self.as_(self.prof)
        r = self.client.post(
            "/api/bookings",
            {
                "resource": self.lab.id, "start": at(1, 16).isoformat(), "end": at(1, 17).isoformat(), "title": "Tut",
                "recurrence": {"freq": "weekly", "count": 3, "conflict_policy": "skip"},
            },
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(len(r.data["created"]), 3)

    def test_approval_flow_over_http(self):
        wf = ApprovalWorkflow.objects.create(name="wf", resource_type=self.rtype, requester_roles=[Role.STUDENT])
        ApprovalStep.objects.create(workflow=wf, order=1, name="Custodian", approver_role=Role.CUSTODIAN)
        self.as_(self.student)
        r = self.client.post(
            "/api/bookings", {"resource": self.lab.id, "start": at(1, 10).isoformat(), "end": at(1, 11).isoformat(), "title": "x"},
            format="json",
        )
        self.assertEqual(r.data["status"], "pending")
        self.assertEqual(self.client.post(f"/api/bookings/{r.data['id']}/approve").status_code, 403)
        self.as_(self.custodian)
        queue = self.client.get("/api/approvals/queue").data
        self.assertEqual([q["id"] for q in queue], [r.data["id"]])
        d = self.client.post(f"/api/bookings/{r.data['id']}/approve", {"comment": "ok"}, format="json")
        self.assertEqual(d.data["booking"]["status"], "confirmed")
        self.assertTrue(Notification.objects.filter(user=self.student, kind="approved").exists())

    def test_scan_checkin_and_checkout(self):
        start = timezone.now().replace(second=0, microsecond=0) - timedelta(minutes=2)
        b = _insert(self.student, self.lab, start, start + timedelta(hours=1), title="now")
        self.as_(self.student)
        r = self.client.post("/api/bookings/scan", {"code": f"http://x/scan?r={self.lab.checkin_token}"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["status"], "checked_in")
        out = self.client.post(f"/api/bookings/{b.id}/check-out")
        self.assertEqual(out.data["status"], "completed")

    def test_custodian_scans_pass(self):
        start = timezone.now().replace(second=0, microsecond=0)
        b = _insert(self.student, self.lab, start, start + timedelta(hours=1), title="now")
        self.as_(self.custodian)
        r = self.client.post("/api/bookings/scan", {"code": f"BMC:{b.id}:{b.qr_token}"}, format="json")
        self.assertEqual(r.data["checkin"]["method"], "booking_qr")

    def test_calendar_feed_is_token_protected(self):
        _insert(self.student, self.lab, at(1, 10), at(1, 11), title="feed me")
        r = self.client.get(f"/api/calendar/{self.student.calendar_token}.ics")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"feed me", r.content)

    # ------------------------------------------------------------- no-shows
    def test_noshow_monitor_waive_and_lift(self):
        b = Booking.objects.create(resource=self.lab, user=self.student, title="x", period=(at(-1, 10), at(-1, 11)), status="released")
        ns = NoShow.objects.create(booking=b, user=self.student, resource=self.lab)
        self.student.restricted_until = timezone.now() + timedelta(days=3)
        self.student.save()
        self.as_(self.manager)
        self.assertEqual(len(self.client.get("/api/users/restricted").data), 1)
        self.client.post(f"/api/noshows/{ns.id}/waive")
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_restricted)

    # ------------------------------------------------------------- operations
    def test_maintenance_and_breakdown(self):
        self.as_(self.manager)
        r = self.client.post(
            "/api/maintenance", {"resource": self.lab.id, "start": at(2, 9).isoformat(), "end": at(2, 12).isoformat(), "title": "AMC"},
            format="json",
        )
        self.assertEqual(r.status_code, 201)
        self.as_(self.student)
        rep = self.client.post("/api/maintenance/report", {"resource": self.lab.id, "title": "Projector dead", "hours": 2}, format="json")
        self.assertEqual(rep.status_code, 201)
        self.lab.refresh_from_db()
        self.assertEqual(self.lab.status, "down")
        self.as_(self.manager)
        self.client.post(f"/api/maintenance/{rep.data['id']}/resolve")
        self.lab.refresh_from_db()
        self.assertEqual(self.lab.status, "active")

    def test_consumables_issue_and_return(self):
        c = Consumable.objects.create(name="Gloves", sku="G1", stock=3, reorder_level=1, kind="accessory")
        b = _insert(self.student, self.lab, at(1, 10), at(1, 11), title="x")
        self.as_(self.student)
        r = self.client.post("/api/issuances", {"consumable": c.id, "quantity": 2, "booking": b.id}, format="json")
        self.assertEqual(r.status_code, 201)
        over = self.client.post("/api/issuances", {"consumable": c.id, "quantity": 5}, format="json")
        self.assertEqual(over.status_code, 409)
        self.as_(self.manager)
        self.client.post(f"/api/issuances/{r.data['id']}/return")
        c.refresh_from_db()
        self.assertEqual(c.stock, 3)

    def test_timetable_webhook_requires_token(self):
        day = timezone.localdate() + timedelta(days=1)
        payload = {
            "label": "v1", "term_start": day.isoformat(), "term_end": (day + timedelta(days=14)).isoformat(),
            "entries": [{"resource_code": "LAB-1", "weekday": day.weekday(), "start": "10:00", "end": "11:00", "course_code": "CSE326"}],
        }
        self.assertEqual(self.client.post("/api/timetable/publish", payload, format="json").status_code, 403)
        r = self.client.post("/api/timetable/publish", payload, format="json", HTTP_X_TIMETABLE_TOKEN="p13-secret")
        self.assertEqual(r.status_code, 201)
        again = self.client.post("/api/timetable/publish", payload, format="json", HTTP_X_TIMETABLE_TOKEN="p13-secret")
        self.assertEqual((again.status_code, again.data["changed"]), (200, False))

    def test_workflow_builder_and_policy_permissions(self):
        self.as_(self.custodian)
        body = {"name": "New", "resource_type": self.rtype.id, "requester_roles": [], "steps": [{"name": "HoD", "approver_role": "dept_head", "sla_hours": 24}]}
        self.assertEqual(self.client.post("/api/workflows", body, format="json").status_code, 403)
        self.assertEqual(self.client.patch("/api/policy", {"grace_minutes": 5}, format="json").status_code, 403)
        self.as_(self.manager)
        self.assertEqual(self.client.post("/api/workflows", body, format="json").status_code, 201)
        self.assertEqual(self.client.patch("/api/policy", {"grace_minutes": 10}, format="json").data["grace_minutes"], 10)

    def test_rules_blackouts_quotas_crud(self):
        self.as_(self.manager)
        r = self.client.post(
            "/api/blackouts", {"title": "Diwali", "start_at": at(3, 0).isoformat(), "end_at": at(4, 0).isoformat()}, format="json"
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.assertEqual(self.client.post("/api/quotas", {"department": self.dept.id, "department_hours_per_week": 10}, format="json").status_code, 201)
        self.assertEqual(self.client.get("/api/availability-rules").status_code, 200)

    def test_analytics_endpoints(self):
        Booking.objects.create(resource=self.lab, user=self.student, title="x", period=(at(-2, 10), at(-2, 12)), status="completed")
        self.as_(self.manager)
        for path in ("dashboard", "utilisation", "heatmap", "noshows", "demand", "approvals", "downtime", "quotas"):
            r = self.client.get(f"/api/analytics/{path}")
            self.assertEqual(r.status_code, 200, path)
        util = self.client.get("/api/analytics/utilisation").data
        self.assertGreater(util["totals"]["used_hours"], 0)
        self.as_(self.student)
        self.assertEqual(self.client.get("/api/analytics/utilisation").status_code, 403)

    def test_notifications_read(self):
        Notification.objects.create(user=self.student, title="Hi")
        self.as_(self.student)
        self.assertEqual(self.client.get("/api/notifications").data["unread"], 1)
        self.client.post("/api/notifications/read-all")
        self.assertEqual(self.client.get("/api/notifications").data["unread"], 0)

    def test_scheduler_command_runs(self):
        call_command("run_scheduler", once=True)


class AdminCompletenessTest(APITestCase):
    """People directory, master data guards, live notifications, health + sweeper heartbeat."""

    def setUp(self):
        self.dept, self.rtype, self.lab, self.custodian = make_campus()
        self.student = make_user("stud", Role.STUDENT, self.dept)
        self.manager = make_user("mgr", Role.FACILITY_MANAGER, self.dept)

    def test_only_policy_admins_edit_people(self):
        self.client.force_authenticate(self.custodian)
        self.assertEqual(self.client.get("/api/users", {"directory": 1}).status_code, 200)
        self.assertEqual(self.client.patch(f"/api/users/{self.student.id}", {"role": "custodian"}, format="json").status_code, 403)
        self.client.force_authenticate(self.manager)
        r = self.client.patch(f"/api/users/{self.student.id}", {"role": "custodian"}, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.student.refresh_from_db()
        self.assertEqual(self.student.role, Role.CUSTODIAN)

    def test_cannot_change_own_role_or_deactivate_self(self):
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.patch(f"/api/users/{self.manager.id}", {"role": "student"}, format="json").status_code, 400)
        self.assertEqual(self.client.patch(f"/api/users/{self.manager.id}", {"is_active": False}, format="json").status_code, 400)

    def test_create_account_with_password(self):
        self.client.force_authenticate(self.manager)
        r = self.client.post(
            "/api/users",
            {"username": "12215634", "first_name": "New", "role": "student", "department": self.dept.id, "password": "s3cret-pass"},
            format="json",
        )
        self.assertEqual(r.status_code, 201, r.data)
        self.client.force_authenticate(None)
        login = self.client.post("/api/auth/login", {"username": "12215634", "password": "s3cret-pass"}, format="json")
        self.assertEqual(login.status_code, 200)

    def test_deleting_type_in_use_is_409(self):
        self.client.force_authenticate(self.manager)
        r = self.client.delete(f"/api/resource-types/{self.rtype.id}")
        self.assertEqual((r.status_code, r.data["error"]), (409, "in_use"))

    def test_location_pin_is_editable(self):
        self.client.force_authenticate(self.manager)
        r = self.client.post("/api/locations", {"building": "Block 37", "latitude": "31.255", "longitude": "75.705"}, format="json")
        self.assertEqual(r.status_code, 201, r.data)

    def test_health_and_sweeper_heartbeat(self):
        from apps.bookings.sweeper import sweep_once
        from apps.rules.models import Policy

        self.client.force_authenticate(self.manager)
        self.assertFalse(self.client.get("/api/system/health").data["sweeper"]["healthy"])
        sweep_once()
        self.assertIsNotNone(Policy.get().last_sweep_at)
        self.assertTrue(self.client.get("/api/system/health").data["sweeper"]["healthy"])

    def test_notification_stream(self):
        from rest_framework_simplejwt.tokens import AccessToken

        self.assertEqual(self.client.get("/api/notifications/stream").status_code, 401)
        token = str(AccessToken.for_user(self.student))
        r = self.client.get("/api/notifications/stream", {"token": token})
        self.assertEqual(r["Content-Type"], "text/event-stream")
        chunks = iter(r.streaming_content)
        self.assertIn(b"retry", next(chunks))
        Notification.objects.create(user=self.student, title="Approved: AI Lab")
        self.assertIn(b"Approved: AI Lab", next(chunks))
