from datetime import datetime, time, timedelta
from typing import Any, Dict, List, Optional, Tuple

from django.db.models import Count, Q
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.accounts.models import User
from apps.approvals.models import ApprovalWorkflow
from apps.bookings.exceptions import BookingError
from apps.bookings.models import Booking, BookingSlot
from apps.bookings import services as booking_services
from apps.catalogue.models import Location, Resource
from apps.maintenance import services as maintenance_services
from apps.maintenance.models import MaintenanceWindow


# OpenAI / Groq standard JSON Tool Schemas
COPILOT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_rooms",
            "description": "Search campus resources and rooms matching criteria like block/building, capacity, equipment/features, and optional date/time window.",
            "parameters": {
                "type": "object",
                "properties": {
                    "building": {
                        "type": "string",
                        "description": "Campus block or building name (e.g., 'Block 34', 'Block 38', 'Block 32', 'Central Library', 'Uni-Mall').",
                    },
                    "min_capacity": {
                        "type": "integer",
                        "description": "Minimum seating capacity required.",
                    },
                    "features": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of desired equipment or features, such as 'Projector', 'Smart Board', 'Whiteboard', 'Video Conference', 'Sound System', 'AC'.",
                    },
                    "room_type": {
                        "type": "string",
                        "description": "Type of room: 'Classroom', 'Computer Lab', 'Seminar Hall', 'Auditorium', 'Conference Room', 'Study Carrel'.",
                    },
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format (or 'today', 'tomorrow').",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Start time in HH:MM format (24-hour, e.g., '14:00' for 2 PM).",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End time in HH:MM format (24-hour, e.g., '16:00' for 4 PM).",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_room_schedule",
            "description": "Check the schedule, existing bookings, and free slots for a specific room on a given date.",
            "parameters": {
                "type": "object",
                "properties": {
                    "room_query": {
                        "type": "string",
                        "description": "Room code (e.g. '34-204') or room name / ID.",
                    },
                    "date": {
                        "type": "string",
                        "description": "Date in YYYY-MM-DD format (or 'today', 'tomorrow').",
                    },
                },
                "required": ["room_query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_my_bookings",
            "description": "Fetch the current logged-in user's upcoming or past bookings, reference numbers, and current approval statuses.",
            "parameters": {
                "type": "object",
                "properties": {
                    "filter_scope": {
                        "type": "string",
                        "enum": ["upcoming", "past", "all"],
                        "description": "Whether to return upcoming active bookings, past history, or all bookings. Defaults to 'upcoming'.",
                    }
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "book_room",
            "description": "Book a specific room for a meeting, study session, class, or event on behalf of the user.",
            "parameters": {
                "type": "object",
                "properties": {
                    "room_query": {
                        "type": "string",
                        "description": "Room code (e.g. '34-204') or room ID.",
                    },
                    "date": {
                        "type": "string",
                        "description": "Booking date in YYYY-MM-DD format (or 'today', 'tomorrow').",
                    },
                    "start_time": {
                        "type": "string",
                        "description": "Start time in HH:MM format (24-hour, e.g., '14:00').",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End time in HH:MM format (24-hour, e.g., '16:00').",
                    },
                    "title": {
                        "type": "string",
                        "description": "Title or event name for the booking.",
                    },
                    "purpose": {
                        "type": "string",
                        "description": "Brief description of the purpose or agenda.",
                    },
                    "attendees": {
                        "type": "integer",
                        "description": "Expected number of attendees (default 1).",
                    },
                },
                "required": ["room_query", "date", "start_time", "end_time", "title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cancel_booking",
            "description": "Cancel an existing booking owned by the user using the booking reference code (e.g., 'BMC-ABC123') or booking ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "booking_reference": {
                        "type": "string",
                        "description": "The reference code (e.g., 'BMC-ABC123') or numeric booking ID to cancel.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Reason for cancellation.",
                    },
                },
                "required": ["booking_reference"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "report_maintenance",
            "description": "Report broken equipment, facility issue, or request maintenance for a campus room.",
            "parameters": {
                "type": "object",
                "properties": {
                    "room_query": {
                        "type": "string",
                        "description": "Room code (e.g. '34-204') or room name.",
                    },
                    "issue_title": {
                        "type": "string",
                        "description": "Summary of the breakdown or defect (e.g. 'Projector HDMI port broken', 'AC water leakage').",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Additional details for the maintenance technicians.",
                    },
                    "severity": {
                        "type": "string",
                        "enum": ["breakdown", "scheduled"],
                        "description": "Severity: 'breakdown' marks the room out of service; 'scheduled' logs planned maintenance. Defaults to 'breakdown'.",
                    },
                },
                "required": ["room_query", "issue_title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_campus_overview",
            "description": "Get real-time vacancy stats and building occupancy summary across Lovely Professional University (LPU) campus blocks right now.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
            },
        },
    },
]


def _parse_user_date(date_str: Optional[str]) -> datetime.date:
    now = timezone.localtime(timezone.now())
    if not date_str or date_str.lower() in ("today", "now"):
        return now.date()
    if date_str.lower() == "tomorrow":
        return now.date() + timedelta(days=1)
    parsed = parse_date(date_str)
    return parsed if parsed else now.date()


def _resolve_time_range(date_val: datetime.date, start_str: str, end_str: str) -> Tuple[datetime, datetime]:
    start_parts = [int(p) for p in start_str.split(":")]
    end_parts = [int(p) for p in end_str.split(":")]
    start_time = time(start_parts[0], start_parts[1])
    end_time = time(end_parts[0], end_parts[1])

    tz = timezone.get_current_timezone()
    start_dt = timezone.make_aware(datetime.combine(date_val, start_time), tz)
    end_dt = timezone.make_aware(datetime.combine(date_val, end_time), tz)
    return start_dt, end_dt


def _find_resource(query: str) -> Optional[Resource]:
    query = str(query).strip()
    if query.isdigit():
        r = Resource.objects.filter(id=int(query)).first()
        if r:
            return r
    # Exact code match
    r = Resource.objects.filter(code__iexact=query).first()
    if r:
        return r
    # Name match
    r = Resource.objects.filter(name__icontains=query).first()
    if r:
        return r
    # Fallback search by room number in location
    return Resource.objects.filter(
        Q(code__icontains=query) | Q(location__room__icontains=query) | Q(location__building__icontains=query)
    ).first()


def tool_search_rooms(args: Dict[str, Any], user: User) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    qs = Resource.objects.filter(status=Resource.Status.ACTIVE).select_related("type", "location", "department")

    building = args.get("building")
    if building:
        qs = qs.filter(location__building__icontains=building)

    min_capacity = args.get("min_capacity")
    if min_capacity:
        qs = qs.filter(capacity__gte=int(min_capacity))

    features = args.get("features")
    if features and isinstance(features, list):
        for f in features:
            qs = qs.filter(features__icontains=f)

    room_type = args.get("room_type")
    if room_type:
        qs = qs.filter(Q(type__name__icontains=room_type) | Q(type__slug__icontains=room_type))

    # Time availability check
    date_str = args.get("date")
    start_str = args.get("start_time")
    end_str = args.get("end_time")
    time_window_str = ""

    if start_str and end_str:
        d = _parse_user_date(date_str)
        try:
            s_dt, e_dt = _resolve_time_range(d, start_str, end_str)
            busy_ids = BookingSlot.objects.filter(period__overlap=(s_dt, e_dt)).values_list("resource_id", flat=True)
            qs = qs.exclude(id__in=busy_ids)
            time_window_str = f" from {s_dt.strftime('%d %b %H:%M')} to {e_dt.strftime('%H:%M')}"
        except Exception:
            pass

    rooms_list = list(qs[:6])

    # Check workflow requirements for current user role
    role = getattr(user, "role", None)
    wf_types = set(
        ApprovalWorkflow.objects.filter(is_active=True, steps__isnull=False)
        .filter(Q(requester_roles=[]) | Q(requester_roles__contains=[role]))
        .values_list("resource_type_id", flat=True)
    )

    results_data = []
    card_rooms = []
    for r in rooms_list:
        needs_approval = r.type_id in wf_types
        info = {
            "id": r.id,
            "code": r.code,
            "name": r.name,
            "building": r.location.building if r.location else "Main Campus",
            "floor": r.location.floor if r.location else "G",
            "room": r.location.room if r.location else "",
            "capacity": r.capacity,
            "type": r.type.name,
            "features": r.features or [],
            "requires_approval": needs_approval,
            "image": r.cover or "/placeholder.png",
        }
        results_data.append(info)
        card_rooms.append(info)

    ui_card = {
        "type": "room_list",
        "title": f"Available Rooms ({len(results_data)} found){time_window_str}",
        "rooms": card_rooms,
    } if card_rooms else None

    return {
        "count": len(results_data),
        "time_window": time_window_str.strip(),
        "rooms": results_data,
        "message": f"Found {len(results_data)} matching rooms." if results_data else "No vacant rooms matched your criteria for that slot.",
    }, ui_card


def tool_check_room_schedule(args: Dict[str, Any], user: User) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    resource = _find_resource(args.get("room_query", ""))
    if not resource:
        return {"error": f"Room '{args.get('room_query')}' was not found."}, None

    d = _parse_user_date(args.get("date"))
    tz = timezone.get_current_timezone()
    day_start = timezone.make_aware(datetime.combine(d, time(0, 0)), tz)
    day_end = timezone.make_aware(datetime.combine(d, time(23, 59, 59)), tz)

    slots = BookingSlot.objects.filter(
        resource=resource,
        period__overlap=(day_start, day_end),
    ).order_by("period")

    schedule_list = []
    for s in slots:
        start_local = timezone.localtime(s.period.lower)
        end_local = timezone.localtime(s.period.upper)
        schedule_list.append({
            "start": start_local.strftime("%H:%M"),
            "end": end_local.strftime("%H:%M"),
            "label": s.label or s.get_kind_display(),
            "kind": s.kind,
        })

    return {
        "room": {
            "id": resource.id,
            "code": resource.code,
            "name": resource.name,
            "building": resource.location.building if resource.location else "",
            "capacity": resource.capacity,
        },
        "date": d.isoformat(),
        "busy_slots": schedule_list,
        "total_busy_slots": len(schedule_list),
        "is_all_day_free": len(schedule_list) == 0,
    }, None


def tool_get_my_bookings(args: Dict[str, Any], user: User) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    scope = args.get("filter_scope", "upcoming")
    qs = Booking.objects.filter(user=user).select_related("resource__location", "resource__type").order_by("-period")

    now = timezone.now()
    if scope == "upcoming":
        qs = qs.filter(period__endswith__gt=now, status__in=Booking.ACTIVE)
    elif scope == "past":
        qs = qs.filter(Q(period__endswith__lte=now) | ~Q(status__in=Booking.ACTIVE))

    bookings_data = []
    card_bookings = []
    for b in qs[:6]:
        start_local = timezone.localtime(b.period.lower)
        end_local = timezone.localtime(b.period.upper)
        item = {
            "id": b.id,
            "reference": b.reference,
            "title": b.title,
            "resource_code": b.resource.code,
            "resource_name": b.resource.name,
            "building": b.resource.location.building if b.resource.location else "",
            "date": start_local.strftime("%a, %d %b %Y"),
            "time": f"{start_local.strftime('%H:%M')} – {end_local.strftime('%H:%M')}",
            "status": b.status,
            "status_label": b.get_status_display(),
            "attendees": b.attendees,
        }
        bookings_data.append(item)
        card_bookings.append(item)

    ui_card = {
        "type": "booking_list",
        "title": f"My {scope.capitalize()} Bookings ({len(bookings_data)})",
        "bookings": card_bookings,
    } if card_bookings else None

    return {
        "count": len(bookings_data),
        "scope": scope,
        "bookings": bookings_data,
        "message": f"Found {len(bookings_data)} {scope} bookings.",
    }, ui_card


def tool_book_room(args: Dict[str, Any], user: User) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    resource = _find_resource(args.get("room_query", ""))
    if not resource:
        return {"error": f"Room '{args.get('room_query')}' not found."}, None

    d = _parse_user_date(args.get("date"))
    start_str = args.get("start_time", "10:00")
    end_str = args.get("end_time", "11:00")
    u_name = user.get_full_name() or user.username
    title = args.get("title") or f"Booking for {u_name}"
    purpose = args.get("purpose", "Booked via AI Campus Copilot")
    attendees = int(args.get("attendees", 1))

    try:
        start_dt, end_dt = _resolve_time_range(d, start_str, end_str)
    except Exception as e:
        return {"error": f"Invalid start or end time: {e}"}, None

    try:
        booking = booking_services.create_booking(
            user=user,
            resource=resource,
            start=start_dt,
            end=end_dt,
            title=title,
            purpose=purpose,
            attendees=attendees,
        )
    except BookingError as exc:
        return {
            "success": False,
            "error_code": exc.code,
            "message": exc.message,
        }, None
    except Exception as exc:
        return {
            "success": False,
            "error": str(exc),
            "message": f"Could not complete booking: {exc}",
        }, None

    booking_info = {
        "id": booking.id,
        "reference": booking.reference,
        "title": booking.title,
        "resource_code": resource.code,
        "resource_name": resource.name,
        "building": resource.location.building if resource.location else "",
        "date": timezone.localtime(start_dt).strftime("%a, %d %b %Y"),
        "time": f"{timezone.localtime(start_dt).strftime('%H:%M')} – {timezone.localtime(end_dt).strftime('%H:%M')}",
        "status": booking.status,
        "status_label": booking.get_status_display(),
        "attendees": booking.attendees,
    }

    ui_card = {
        "type": "booking_success",
        "title": "Booking Created Successfully!",
        "booking": booking_info,
    }

    return {
        "success": True,
        "message": f"Successfully reserved {resource.name} ({booking.reference}). Status: {booking.get_status_display()}.",
        "booking": booking_info,
    }, ui_card


def tool_cancel_booking(args: Dict[str, Any], user: User) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    ref = args.get("booking_reference", "").strip()
    qs = Booking.objects.filter(Q(reference__iexact=ref) | (Q(id=int(ref)) if ref.isdigit() else Q(pk=None)))
    if not user.is_manager:
        qs = qs.filter(user=user)
    booking = qs.first()
    if not booking:
        return {"error": f"Booking '{ref}' not found or you do not have permission to cancel it."}, None

    reason = args.get("reason", "Cancelled by user via Campus Copilot")
    try:
        updated_b = booking_services.cancel(booking, user, reason)
        return {
            "success": True,
            "message": f"Booking {updated_b.reference} for {updated_b.resource.name} has been cancelled.",
            "reference": updated_b.reference,
            "status": updated_b.status,
        }, None
    except BookingError as exc:
        return {"success": False, "message": exc.message}, None


def tool_report_maintenance(args: Dict[str, Any], user: User) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    resource = _find_resource(args.get("room_query", ""))
    if not resource:
        return {"error": f"Room '{args.get('room_query')}' was not found."}, None

    issue_title = args.get("issue_title", "Unspecified facility issue")
    notes = args.get("notes", "Reported via AI Copilot")
    sev = args.get("severity", "breakdown")
    kind = MaintenanceWindow.Kind.BREAKDOWN if sev == "breakdown" else MaintenanceWindow.Kind.SCHEDULED

    now = timezone.now()
    end_time = now + timedelta(hours=3)

    try:
        window = maintenance_services.schedule(
            resource=resource,
            start=now,
            end=end_time,
            title=issue_title,
            kind=kind,
            notes=notes,
            by=user,
        )
        ticket_info = {
            "id": window.id,
            "room_code": resource.code,
            "room_name": resource.name,
            "title": issue_title,
            "kind": kind,
            "status": window.status,
            "displaced_bookings": window.displaced_bookings,
        }
        ui_card = {
            "type": "maintenance_ticket",
            "title": f"Maintenance Ticket Logged #{window.id}",
            "ticket": ticket_info,
        }
        return {
            "success": True,
            "message": f"Logged ticket #{window.id} for {resource.name}. Custodians have been notified.",
            "ticket": ticket_info,
        }, ui_card
    except Exception as exc:
        return {"success": False, "error": str(exc)}, None


def tool_get_campus_overview(args: Dict[str, Any], user: User) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    now = timezone.now()
    hour_end = now + timedelta(hours=1)

    locations = Location.objects.values("building").annotate(total_rooms=Count("resources")).filter(total_rooms__gt=0)
    busy_rooms = set(BookingSlot.objects.filter(period__overlap=(now, hour_end)).values_list("resource_id", flat=True))

    buildings_summary = []
    for loc in locations:
        b_name = loc["building"]
        rooms_in_b = Resource.objects.filter(location__building=b_name, status=Resource.Status.ACTIVE)
        total = rooms_in_b.count()
        if total == 0:
            continue
        busy_count = rooms_in_b.filter(id__in=busy_rooms).count()
        vacant_count = max(0, total - busy_count)
        vacant_pct = round((vacant_count / total) * 100) if total else 0

        buildings_summary.append({
            "building": b_name,
            "total_rooms": total,
            "vacant_rooms": vacant_count,
            "occupied_rooms": busy_count,
            "vacant_percentage": f"{vacant_pct}%",
        })

    buildings_summary.sort(key=lambda x: int(x["vacant_percentage"].replace("%", "")), reverse=True)

    return {
        "timestamp": timezone.localtime(now).strftime("%d %b %Y, %H:%M"),
        "buildings": buildings_summary,
        "most_available": buildings_summary[0]["building"] if buildings_summary else "N/A",
    }, None


TOOL_DISPATCHER = {
    "search_rooms": tool_search_rooms,
    "check_room_schedule": tool_check_room_schedule,
    "get_my_bookings": tool_get_my_bookings,
    "book_room": tool_book_room,
    "cancel_booking": tool_cancel_booking,
    "report_maintenance": tool_report_maintenance,
    "get_campus_overview": tool_get_campus_overview,
}


def execute_tool(name: str, arguments: Dict[str, Any], user: User) -> Tuple[Dict[str, Any], Optional[Dict[str, Any]]]:
    fn = TOOL_DISPATCHER.get(name)
    if not fn:
        return {"error": f"Unknown tool: {name}"}, None
    try:
        return fn(arguments, user)
    except Exception as exc:
        return {"error": f"Tool execution failed: {exc}"}, None
