import csv
import io
import ipaddress
from datetime import timedelta
from urllib.parse import urlparse

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.accounts.models import Department
from apps.accounts.permissions import IsManager, ReadOnlyOrManager, ReadOnlyOrPolicyAdmin
from apps.approvals.models import ApprovalWorkflow
from apps.bookings.exceptions import BookingError
from apps.bookings.models import BookingSlot, SlotWatch
from apps.rules.services import availability, validate_request

from .models import Location, Resource, ResourceImage, ResourceType
from .serializers import (
    LocationSerializer,
    ResourceDetailSerializer,
    ResourceImageSerializer,
    ResourceListSerializer,
    ResourceTypeSerializer,
)


def share_base(request):
    """
    Where a QR code's link should point. Normally the configured frontend. A page may ask for its own
    address instead, so codes made on a PC running the app locally open on a phone on the same Wi-Fi.
    Only the configured frontend, the CORS origins and, in DEBUG, private network addresses are accepted,
    so a code can never be made to send people to some other site.
    """
    default = settings.FRONTEND_URL.rstrip("/")
    asked = str(request.query_params.get("origin", "")).rstrip("/")
    if not asked or asked == default:
        return default
    if asked in {o.rstrip("/") for o in settings.CORS_ALLOWED_ORIGINS}:
        return asked
    if settings.DEBUG:
        parsed = urlparse(asked)
        try:
            ip = ipaddress.ip_address(parsed.hostname or "")
        except ValueError:
            ip = None
        if parsed.scheme in ("http", "https") and not parsed.path and ip and (ip.is_private or ip.is_loopback):
            return f"{parsed.scheme}://{parsed.netloc}"
    return default


def qr_svg(data, box=12):
    img = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, box_size=box, border=2)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue()


class ResourceTypeViewSet(viewsets.ModelViewSet):
    serializer_class = ResourceTypeSerializer
    permission_classes = [ReadOnlyOrPolicyAdmin]

    def get_queryset(self):
        return ResourceType.objects.annotate(resource_count=Count("resources", filter=~Q(resources__status="retired")))


class LocationViewSet(viewsets.ModelViewSet):
    queryset = Location.objects.all()
    serializer_class = LocationSerializer
    permission_classes = [ReadOnlyOrManager]


class ResourceViewSet(viewsets.ModelViewSet):
    """
    Catalogue with faceted search. Extra query params:
      q, type (slug or id, comma list), department, building, min_capacity, features (comma list),
      free_from + free_to → only resources with nothing in the occupancy ledger over that window,
      saved=1 → only the rooms the signed-in user has saved.
    """

    permission_classes = [ReadOnlyOrManager]

    def get_serializer_class(self):
        return ResourceListSerializer if self.action == "list" else ResourceDetailSerializer

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        # "Needs approval" depends on who is looking: a workflow may only apply to some requester roles.
        role = getattr(self.request.user, "role", None)
        ctx["wf_types"] = set(
            ApprovalWorkflow.objects.filter(is_active=True, steps__isnull=False)
            .filter(Q(requester_roles=[]) | Q(requester_roles__contains=[role]))
            .values_list("resource_type_id", flat=True)
        )
        if self.request.user.is_authenticated:
            ctx["saved_ids"] = set(self.request.user.saved_resources.values_list("id", flat=True))
        return ctx

    def get_queryset(self):
        qs = Resource.objects.select_related("type", "department", "location").prefetch_related("images")
        p = self.request.query_params
        if self.action == "list" and p.get("include_retired") != "1":
            qs = qs.exclude(status=Resource.Status.RETIRED)
        if q := p.get("q"):
            qs = qs.filter(
                Q(name__icontains=q) | Q(code__icontains=q) | Q(description__icontains=q)
                | Q(features__icontains=q) | Q(location__building__icontains=q) | Q(type__name__icontains=q)
                | Q(attributes__value__icontains=q)
            ).distinct()
        if t := p.get("type"):
            vals = t.split(",")
            ids = [v for v in vals if v.isdigit()]
            qs = qs.filter(Q(type__slug__in=vals) | Q(type_id__in=ids))
        if d := p.get("department"):
            vals = d.split(",")
            qs = qs.filter(Q(department__code__in=vals) | Q(department_id__in=[x for x in vals if x.isdigit()]))
        if b := p.get("building"):
            qs = qs.filter(location__building__in=b.split(","))
        if c := p.get("min_capacity"):
            qs = qs.filter(capacity__gte=int(c))
        if f := p.get("features"):
            qs = qs.filter(features__contains=f.split(","))
        if p.get("mine") == "1":
            qs = qs.filter(custodians=self.request.user)
        if p.get("saved") == "1":
            qs = qs.filter(saved_by=self.request.user)
        ff, ft = p.get("free_from"), p.get("free_to")
        if ff and ft:
            s, e = parse_datetime(ff), parse_datetime(ft)
            if s and e:
                busy = BookingSlot.objects.filter(period__overlap=(s, e)).values("resource_id")
                qs = qs.exclude(id__in=busy).filter(status=Resource.Status.ACTIVE)
        return qs.order_by("type__name", "name")

    @action(detail=True, methods=["post", "delete"], url_path="saved", permission_classes=[IsAuthenticated])
    def saved(self, request, pk=None):
        """Any signed-in user can save a room for themselves. Repeating either call changes nothing."""
        resource = self.get_object()
        if request.method == "POST":
            request.user.saved_resources.add(resource)
        else:
            request.user.saved_resources.remove(resource)
        return Response({"is_saved": request.method == "POST"})

    def _requested_slot(self, data):
        start, end = parse_datetime(str(data.get("start", ""))), parse_datetime(str(data.get("end", "")))
        if not start or not end or end <= start:
            raise BookingError("bad_slot", "That isn't a valid time range.")
        return start, end

    @action(detail=True, methods=["get"], url_path="alternatives", permission_classes=[IsAuthenticated])
    def alternatives(self, request, pk=None):
        """A slot is taken, so: similar rooms the asker could book for that exact time, and the next free time here."""
        resource = self.get_object()
        start, end = self._requested_slot(request.query_params)
        busy = BookingSlot.objects.filter(period__overlap=(start, end)).values("resource_id")
        candidates = (
            Resource.objects.filter(type_id=resource.type_id, status=Resource.Status.ACTIVE)
            .exclude(id=resource.id)
            .exclude(id__in=busy)
            .select_related("type", "department", "location")
            .prefetch_related("images")
        )
        same_building = resource.location.building if resource.location else None
        ranked = sorted(candidates, key=lambda r: (r.location is None or r.location.building != same_building, abs(r.capacity - resource.capacity)))
        rooms = []
        for r in ranked:
            try:
                validate_request(request.user, r, start, end, 1, check_quota=False)
            except BookingError:
                continue
            rooms.append(r)
            if len(rooms) == 4:
                break
        day = timezone.localtime(max(start, timezone.now())).date()
        slots = availability(resource, day, day + timedelta(days=7), request.user)["free"]
        next_free = next((s["start"] for s in slots if s["start"] >= max(start, timezone.now())), None)
        return Response({
            "rooms": ResourceListSerializer(rooms, many=True, context=self.get_serializer_context()).data,
            "next_free": next_free,
        })

    @action(detail=True, methods=["post"], url_path="watch", permission_classes=[IsAuthenticated])
    def watch(self, request, pk=None):
        """Join the waitlist for a slot held by someone else's booking. Repeating it changes nothing."""
        resource = self.get_object()
        start, end = self._requested_slot(request.data)
        if start <= timezone.now():
            raise BookingError("slot_passed", "That time has already passed.")
        allowed = resource.type.allowed_roles
        if allowed and request.user.role not in allowed and not request.user.is_superuser:
            raise BookingError("role_not_permitted", f"{resource.type.name} is booked by staff only, so there is no waitlist for you to join.", http_status=403)
        held = BookingSlot.objects.filter(
            resource=resource, kind=BookingSlot.Kind.BOOKING, period__overlap=(start, end)
        ).exclude(booking__user=request.user)
        if not held.exists():
            raise BookingError("not_held", "Nobody else has booked that time, so there's nothing to wait for.")
        SlotWatch.objects.get_or_create(resource=resource, user=request.user, start=start, end=end)
        return Response({"watching": True}, status=201)

    @action(detail=True, methods=["get"], url_path="insights", permission_classes=[IsAuthenticated])
    def insights(self, request, pk=None):
        """How often each opening hour was taken over the last four weeks, so people can pick a quiet time."""
        resource = self.get_object()
        now = timezone.now()
        since = now - timedelta(days=28)
        today = timezone.localtime(now).date()
        rules = availability(resource, today, today + timedelta(days=1), request.user)["rules"]
        if not rules:
            return Response({"hours": [], "quietest": None})
        open_days = {w for r in rules for w in r["weekdays"]}
        days = sum((today - timedelta(days=i)).weekday() in open_days for i in range(1, 29)) or 1
        first, last = min(int(r["open"][:2]) for r in rules), max(int(r["close"][:2]) for r in rules)
        taken = set()
        for period in BookingSlot.objects.filter(resource=resource, period__overlap=(since, now)).values_list("period", flat=True):
            cur = timezone.localtime(max(period.lower, since)).replace(minute=0, second=0, microsecond=0)
            end = timezone.localtime(min(period.upper, now))
            while cur < end:
                taken.add((cur.date(), cur.hour))
                cur += timedelta(hours=1)
        hours = [
            {"hour": h, "busy": round(sum(1 for _, x in taken if x == h) / days, 2)} for h in range(first, last)
        ]
        quietest = min(hours, key=lambda x: x["busy"])["hour"] if taken and hours else None
        return Response({"hours": hours, "quietest": quietest})

    @action(detail=False)
    def facets(self, request):
        base = Resource.objects.exclude(status=Resource.Status.RETIRED)
        features = {}
        for fl in base.values_list("features", flat=True):
            for f in fl:
                features[f] = features.get(f, 0) + 1
        return Response({
            "types": list(
                base.values("type__id", "type__name", "type__slug", "type__color", "type__icon")
                .annotate(n=Count("id")).order_by("type__name")
            ),
            "departments": list(
                base.exclude(department=None).values("department__code", "department__name")
                .annotate(n=Count("id")).order_by("department__code")
            ),
            "buildings": list(
                base.exclude(location=None).values("location__building").annotate(n=Count("id")).order_by("location__building")
            ),
            "features": sorted(({"name": k, "n": v} for k, v in features.items()), key=lambda x: -x["n"])[:24],
            "max_capacity": max(base.values_list("capacity", flat=True), default=0),
        })

    @action(detail=True, methods=["get"], url_path="availability")
    def availability_view(self, request, pk=None):
        resource = self.get_object()
        start = parse_date(request.query_params.get("from", "")) or timezone.localdate()
        end = parse_date(request.query_params.get("to", "")) or start + timedelta(days=7)
        if (end - start).days > 62:
            raise ValidationError("Range too large (max 62 days).")
        return Response(availability(resource, start, end, viewer=request.user))

    @action(detail=True, methods=["get"], url_path="qr")
    def qr(self, request, pk=None):
        """Printable check-in poster code. Encodes a deep link the mobile scanner understands."""
        r = self.get_object()
        return HttpResponse(qr_svg(f"{share_base(request)}/scan?r={r.checkin_token}"), content_type="image/svg+xml")

    @action(detail=True, methods=["get"], url_path="checkin-token", permission_classes=[IsManager])
    def checkin_token(self, request, pk=None):
        r = self.get_object()
        return Response({"token": str(r.checkin_token), "url": f"{settings.FRONTEND_URL}/scan?r={r.checkin_token}"})

    @action(detail=True, methods=["post"], url_path="images", permission_classes=[IsManager])
    def add_image(self, request, pk=None):
        r = self.get_object()
        img = ResourceImage.objects.create(
            resource=r, image=request.FILES.get("image"), url=request.data.get("url", ""),
            caption=request.data.get("caption", ""), order=r.images.count(),
        )
        return Response(ResourceImageSerializer(img).data, status=201)

    @action(detail=False, methods=["post"], url_path="bulk-import", permission_classes=[IsManager])
    def bulk_import(self, request):
        """
        CSV columns: code,name,type,department,building,floor,room,capacity,features,value_inr,image_url,description
        `features` are separated by '|'. Existing codes are updated, new ones created.
        """
        f = request.FILES.get("file")
        text = f.read().decode("utf-8-sig") if f else request.data.get("csv", "")
        if not text:
            raise ValidationError("Upload a CSV file or send `csv` text.")
        created = updated = 0
        errors = []
        for i, row in enumerate(csv.DictReader(io.StringIO(text)), start=2):
            try:
                with transaction.atomic():
                    tname = (row.get("type") or "").strip()
                    rtype = ResourceType.objects.get(Q(name__iexact=tname) | Q(slug=tname))
                    dept = Department.objects.filter(code__iexact=(row.get("department") or "").strip()).first()
                    loc = None
                    if (row.get("building") or "").strip():
                        loc, _ = Location.objects.get_or_create(
                            building=row["building"].strip(),
                            floor=(row.get("floor") or "").strip(),
                            room=(row.get("room") or "").strip(),
                        )
                    _, was_created = Resource.objects.update_or_create(
                        code=row["code"].strip(),
                        defaults={
                            "name": row["name"].strip(), "type": rtype, "department": dept, "location": loc,
                            "capacity": int(row.get("capacity") or 1),
                            "features": [x.strip() for x in (row.get("features") or "").split("|") if x.strip()],
                            "value_inr": int(row.get("value_inr") or 0),
                            "image_url": (row.get("image_url") or "").strip(),
                            "description": (row.get("description") or "").strip(),
                        },
                    )
                created += was_created
                updated += not was_created
            except Exception as exc:  # report per row and keep going
                errors.append({"row": i, "error": str(exc)})
        return Response({"created": created, "updated": updated, "errors": errors})
