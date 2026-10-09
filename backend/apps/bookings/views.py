from datetime import timedelta

from django.conf import settings
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from ics import Calendar, Event
from rest_framework import mixins, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from apps.accounts.models import User
from apps.accounts.permissions import IsManager
from apps.approvals.services import decide
from apps.catalogue.models import Resource
from apps.catalogue.views import qr_svg
from apps.consumables.services import issue_for_booking

from . import services
from .exceptions import BookingError
from .models import Booking, NoShow
from .serializers import BookingCreateSerializer, BookingDetailSerializer, BookingSerializer, NoShowSerializer


def _ics_event(b):
    e = Event()
    e.name = f"{b.title} — {b.resource.name}"
    e.begin = b.start
    e.end = b.end
    e.uid = f"{b.reference}@bookmycampus"
    e.location = str(b.resource.location or b.resource.name)
    e.description = f"Ref {b.reference} · {b.get_status_display()}\n{settings.FRONTEND_URL}/bookings/{b.id}"
    return e


class BookingViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    GET  /bookings/?scope=mine|all|custodian&status=&resource=&from=&to=
    POST /bookings/                    single or recurring (pass `recurrence`)
    POST /bookings/:id/approve|reject  approval workflow step
    POST /bookings/:id/check-in        {token}  (resource poster QR or booking pass QR)
    POST /bookings/:id/check-out | cancel
    """

    def get_serializer_class(self):
        return BookingDetailSerializer if self.action == "retrieve" else BookingSerializer

    def get_queryset(self):
        u = self.request.user
        qs = Booking.objects.select_related(
            "resource__type", "resource__location", "user", "checkin", "recurrence"
        ).prefetch_related("approvals")
        p = self.request.query_params
        scope = p.get("scope", "mine")
        if self.action != "list":
            if not u.is_manager:
                qs = qs.filter(user=u)
        elif scope == "all" and u.is_manager:
            pass
        elif scope == "custodian" and u.is_manager:
            qs = qs.filter(resource__custodians=u)
        else:
            qs = qs.filter(user=u)
        if s := p.get("status"):
            qs = qs.filter(status__in=s.split(","))
        if r := p.get("resource"):
            qs = qs.filter(resource_id=r)
        if f := p.get("from"):
            if dt := parse_datetime(f):
                qs = qs.filter(period__endswith__gt=dt)
        if t := p.get("to"):
            if dt := parse_datetime(t):
                qs = qs.filter(period__startswith__lt=dt)
        if p.get("upcoming") == "1":
            qs = qs.filter(period__endswith__gt=timezone.now(), status__in=Booking.ACTIVE)
        if p.get("past") == "1":
            qs = qs.filter(Q(period__endswith__lte=timezone.now()) | ~Q(status__in=Booking.ACTIVE)).order_by("-period")
        return qs

    def create(self, request):
        s = BookingCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        resource = get_object_or_404(Resource.objects.select_related("type"), pk=d["resource"])
        common = dict(title=d["title"], purpose=d["purpose"], on_behalf_of=d["on_behalf_of"], attendees=d["attendees"])
        if d.get("recurrence"):
            rec = d["recurrence"]
            rule, created, skipped = services.create_recurring(
                request.user, resource, d["start"], d["end"], **common,
                freq=rec["freq"], interval=rec["interval"], weekdays=rec.get("weekdays"),
                until=rec.get("until"), count=rec.get("count"), conflict_policy=rec["conflict_policy"],
            )
            return Response(
                {
                    "recurrence": rule.id,
                    "created": BookingSerializer(created, many=True).data,
                    "skipped": skipped,
                    "requested": rule.requested_occurrences,
                },
                status=201,
            )
        booking = services.create_booking(request.user, resource, d["start"], d["end"], **common)
        issued = []
        for acc in d.get("accessories") or []:
            try:
                issued.append(issue_for_booking(booking, int(acc["id"]), int(acc.get("quantity", 1)), request.user))
            except BookingError:
                pass  # accessory shortage must not undo a confirmed room booking
        data = BookingDetailSerializer(booking).data
        data["accessories_issued"] = len(issued)
        return Response(data, status=201)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        b = services.cancel(self.get_object(), request.user, request.data.get("reason", ""))
        return Response(BookingSerializer(b).data)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        b = get_object_or_404(Booking, pk=pk)
        n = decide(b, request.user, True, request.data.get("comment", ""), bool(request.data.get("series")))
        b.refresh_from_db()
        return Response({"decided": n, "booking": BookingSerializer(b).data})

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        b = get_object_or_404(Booking, pk=pk)
        n = decide(b, request.user, False, request.data.get("comment", ""), bool(request.data.get("series")))
        b.refresh_from_db()
        return Response({"decided": n, "booking": BookingSerializer(b).data})

    @action(detail=True, methods=["post"], url_path="check-in")
    def check_in(self, request, pk=None):
        b = get_object_or_404(Booking.objects.select_related("resource"), pk=pk)
        b = services.check_in(b, request.user, request.data.get("token", ""))
        return Response(BookingDetailSerializer(b).data)

    @action(detail=True, methods=["post"], url_path="check-out")
    def check_out(self, request, pk=None):
        b = services.check_out(self.get_object(), request.user, request.data.get("note", ""))
        return Response(BookingSerializer(b).data)

    @action(detail=True, methods=["get"], url_path="qr")
    def qr(self, request, pk=None):
        """The booker's pass — a custodian scans this to verify them at the door."""
        b = self.get_object()
        return HttpResponse(qr_svg(f"BMC:{b.id}:{b.qr_token}", box=10), content_type="image/svg+xml")

    @action(detail=True, methods=["get"], url_path="ics")
    def ics(self, request, pk=None):
        b = self.get_object()
        cal = Calendar()
        cal.events.add(_ics_event(b))
        resp = HttpResponse(cal.serialize(), content_type="text/calendar")
        resp["Content-Disposition"] = f'attachment; filename="{b.reference}.ics"'
        return resp

    @action(detail=False, methods=["post"], url_path="scan")
    def scan(self, request):
        """
        Single mobile endpoint for the QR scanner:
          * resource poster  (…/scan?r=<uuid>)  → checks in *your* current booking there
          * booking pass     (BMC:<id>:<uuid>)  → custodian verifies a booker
        """
        raw = str(request.data.get("code", "")).strip()
        if raw.startswith("BMC:"):
            try:
                _, bid, token = raw.split(":", 2)
            except ValueError:
                raise BookingError("bad_token", "Unrecognised booking pass.")
            b = get_object_or_404(Booking.objects.select_related("resource"), pk=int(bid))
            b = services.check_in(b, request.user, token)
        else:
            token = raw.split("r=")[-1].split("&")[0] if "r=" in raw else raw
            b = services.check_in_by_resource_token(request.user, token)
        return Response(BookingDetailSerializer(b).data)

    @action(detail=False, methods=["get"], permission_classes=[IsManager])
    def board(self, request):
        """Live booking board — everything happening today, grouped client-side by resource."""
        today = timezone.localdate()
        start = timezone.make_aware(timezone.datetime.combine(today, timezone.datetime.min.time()))
        qs = (
            Booking.objects.select_related("resource__type", "resource__location", "user", "checkin")
            .prefetch_related("approvals")
            .filter(period__overlap=(start, start + timedelta(days=1)))
            .exclude(status__in=[Booking.Status.CANCELLED, Booking.Status.REJECTED])
            .order_by("period")
        )
        return Response(BookingSerializer(qs, many=True).data)


class NoShowViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = NoShowSerializer
    permission_classes = [IsManager]

    def get_queryset(self):
        return NoShow.objects.select_related("user", "resource", "booking")[:200]

    @action(detail=True, methods=["post"])
    def waive(self, request, pk=None):
        ns = get_object_or_404(NoShow, pk=pk)
        ns.waived = True
        ns.waived_reason = request.data.get("reason", "Waived by manager")[:200]
        ns.save(update_fields=["waived", "waived_reason"])
        # Re-evaluate the ladder; lift the restriction if they've dropped below threshold.
        u = ns.user
        strikes = services.apply_noshow_restriction(u)
        from apps.rules.models import Policy

        if strikes < Policy.get().strike_level1 and u.restricted_until:
            u.restricted_until = None
            u.restriction_reason = ""
            u.save(update_fields=["restricted_until", "restriction_reason"])
        return Response(NoShowSerializer(ns).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def calendar_feed(request, token):
    """Subscribable personal iCal feed: Google / Outlook / Apple Calendar."""
    user = get_object_or_404(User, calendar_token=token)
    cal = Calendar()
    since = timezone.now() - timedelta(days=30)
    for b in Booking.objects.select_related("resource__location").filter(
        user=user, status__in=Booking.ACTIVE + (Booking.Status.COMPLETED,), period__endswith__gte=since
    ):
        cal.events.add(_ics_event(b))
    return HttpResponse(cal.serialize(), content_type="text/calendar")
