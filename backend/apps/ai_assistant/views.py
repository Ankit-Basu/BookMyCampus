from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .agent import copilot_agent


@api_view(["POST"])
@permission_classes([IsAuthenticated])
def chat(request):
    """
    POST /api/ai/chat
    Payload:
      {
        "message": "Find a room with a projector in Block 34 for 30 students today from 4 to 6 PM",
        "history": [{"role": "user", "content": "..."}, {"role": "assistant", "content": "..."}]
      }
    """
    message = request.data.get("message", "").strip()
    if not message:
        return Response({"error": "Message is required."}, status=status.HTTP_400_BAD_REQUEST)

    history = request.data.get("history", [])
    if not isinstance(history, list):
        history = []

    result = copilot_agent.run(
        user=request.user,
        user_message=message,
        history=history,
    )

    return Response(result, status=status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
def suggestions(request):
    """
    GET /api/ai/suggestions
    Returns role-tailored prompt starter chips for the UI.
    """
    role = getattr(request.user, "role", "student")

    if role in ("faculty", "dept_head"):
        items = [
            {"label": "Seminar Hall for 60+", "prompt": "Find a seminar hall for 60 attendees with video conferencing tomorrow"},
            {"label": "My Upcoming Bookings", "prompt": "What are my upcoming bookings and their approval statuses?"},
            {"label": "Block 38 Vacancy", "prompt": "Check the room vacancy and free slots in Block 38 today"},
            {"label": "Report Lab Issue", "prompt": "The HDMI cable is faulty in Room 34-204, please file a maintenance ticket"},
        ]
    elif role in ("custodian", "facility_manager", "admin"):
        items = [
            {"label": "Campus Vacancy Overview", "prompt": "Give me an overview of vacant vs occupied rooms across all campus blocks right now"},
            {"label": "Report Room Breakdown", "prompt": "Log a breakdown ticket for Room 32-101 (AC breakdown)"},
            {"label": "Find Available Classrooms", "prompt": "Find all free classrooms in Block 34 right now"},
            {"label": "Check Room Schedule", "prompt": "Check the complete schedule and bookings for Room 34-101 today"},
        ]
    else:  # student
        items = [
            {"label": "Study Room in Block 34", "prompt": "Find a quiet study room or classroom in Block 34 for 25 people today from 3 PM to 5 PM"},
            {"label": "Rooms with Projector", "prompt": "Which rooms in Block 38 or 36 have a projector and AC?"},
            {"label": "My Bookings", "prompt": "What are my active and upcoming bookings?"},
            {"label": "Most Vacant Block", "prompt": "Which campus block currently has the highest percentage of free rooms?"},
        ]

    return Response({"suggestions": items}, status=status.HTTP_200_OK)
