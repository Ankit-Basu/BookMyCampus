from datetime import time, timedelta
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import Department, Role, User
from apps.bookings.models import Booking
from apps.catalogue.models import Location, Resource, ResourceType
from apps.rules.models import AvailabilityRule
from .groq_client import GroqClient, mask_key
from .tools import (
    execute_tool,
    tool_book_room,
    tool_cancel_booking,
    tool_check_room_schedule,
    tool_get_campus_overview,
    tool_get_my_bookings,
    tool_report_maintenance,
    tool_search_rooms,
)


class AiAssistantTests(TestCase):
    def setUp(self):
        self.dept = Department.objects.create(name="Computer Science & Engineering", code="CSE")
        self.user = User.objects.create_user(
            username="arjun.patel",
            email="arjun.patel@lpu.in",
            first_name="Arjun",
            last_name="Patel",
            role=Role.STUDENT,
            department=self.dept,
        )
        self.manager = User.objects.create_user(
            username="dr.sharma",
            email="dr.sharma@lpu.in",
            first_name="Dr.",
            last_name="Sharma",
            role=Role.DEPT_HEAD,
            department=self.dept,
        )
        self.loc = Location.objects.create(building="Block 34", floor="2", room="204")
        self.rtype = ResourceType.objects.create(name="Classroom", slug="classroom")
        AvailabilityRule.objects.create(
            resource_type=self.rtype,
            weekdays=[0, 1, 2, 3, 4, 5, 6],
            open_time=time(6),
            close_time=time(23),
            min_duration_minutes=30,
            max_duration_minutes=240,
            min_lead_minutes=0,
            max_advance_days=60,
        )
        self.room = Resource.objects.create(
            type=self.rtype,
            code="34-204",
            name="Classroom 34-204",
            location=self.loc,
            capacity=40,
            features=["Projector", "Smart Board", "AC"],
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.user)

    def test_mask_key(self):
        self.assertEqual(mask_key("gsk_1234567890abcdef"), "gsk_123...cdef")
        self.assertEqual(mask_key("short"), "***")

    def test_groq_client_rotation(self):
        with override_settings(GROQ_API_KEYS=["key1_test_sample", "key2_test_sample"]):
            client = GroqClient()
            k1 = client.get_current_key()
            self.assertEqual(k1, "key1_test_sample")
            client.rotate_key("test rotation")
            k2 = client.get_current_key()
            self.assertEqual(k2, "key2_test_sample")
            client.rotate_key("cycle back")
            k3 = client.get_current_key()
            self.assertEqual(k3, "key1_test_sample")

    def test_tool_search_rooms(self):
        res, card = tool_search_rooms({"building": "Block 34", "min_capacity": 30}, self.user)
        self.assertEqual(res["count"], 1)
        self.assertEqual(res["rooms"][0]["code"], "34-204")
        self.assertIsNotNone(card)
        self.assertEqual(card["type"], "room_list")

    def test_tool_check_room_schedule(self):
        res, card = tool_check_room_schedule({"room_query": "34-204", "date": "today"}, self.user)
        self.assertEqual(res["room"]["code"], "34-204")
        self.assertTrue(res["is_all_day_free"])

    def test_tool_book_room_and_cancel(self):
        res, card = tool_book_room(
            {
                "room_query": "34-204",
                "date": "tomorrow",
                "start_time": "14:00",
                "end_time": "15:30",
                "title": "Study Group",
            },
            self.user,
        )
        self.assertTrue(res["success"], f"Failed with: {res}")
        ref = res["booking"]["reference"]
        self.assertTrue(ref.startswith("BMC-"))
        self.assertIsNotNone(card)

        # Verify in DB
        b = Booking.objects.get(reference=ref)
        self.assertEqual(b.user, self.user)

        # Cancel tool
        c_res, _ = tool_cancel_booking({"booking_reference": ref, "reason": "Plans changed"}, self.user)
        self.assertTrue(c_res["success"])
        b.refresh_from_db()
        self.assertEqual(b.status, Booking.Status.CANCELLED)

    def test_tool_get_my_bookings(self):
        # Create a booking
        start = timezone.now() + timedelta(hours=2)
        end = start + timedelta(hours=1)
        Booking.objects.create(
            resource=self.room,
            user=self.user,
            title="AI Lab Discussion",
            period=(start, end),
            status=Booking.Status.CONFIRMED,
        )

        res, card = tool_get_my_bookings({"filter_scope": "upcoming"}, self.user)
        self.assertEqual(res["count"], 1)
        self.assertEqual(res["bookings"][0]["title"], "AI Lab Discussion")
        self.assertIsNotNone(card)

    def test_tool_report_maintenance(self):
        res, card = tool_report_maintenance(
            {"room_query": "34-204", "issue_title": "Projector HDMI broken", "severity": "breakdown"},
            self.user,
        )
        self.assertTrue(res["success"])
        self.assertIsNotNone(card)
        self.assertEqual(card["type"], "maintenance_ticket")

    def test_tool_get_campus_overview(self):
        res, card = tool_get_campus_overview({}, self.user)
        self.assertTrue(len(res["buildings"]) >= 1)
        self.assertEqual(res["buildings"][0]["building"], "Block 34")

    def test_suggestions_endpoint(self):
        resp = self.client.get("/api/ai/suggestions")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue("suggestions" in data)
        self.assertTrue(len(data["suggestions"]) >= 3)

    def test_chat_endpoint_with_mocked_completion(self):
        mock_response = {
            "content": "I found Room 34-204 in Block 34 which matches your requirements.",
            "tool_calls": None,
            "_model_used": "openai/gpt-oss-120b",
            "_key_used_masked": "gsk_123...cdef",
        }
        with patch.object(GroqClient, "chat_completion", return_value=mock_response):
            resp = self.client.post(
                "/api/ai/chat",
                data={"message": "Is there a room with a projector in Block 34?"},
                format="json",
            )
            self.assertEqual(resp.status_code, 200)
            data = resp.json()
            self.assertIn("Room 34-204", data["reply"])
            self.assertEqual(data["model_used"], "openai/gpt-oss-120b")
