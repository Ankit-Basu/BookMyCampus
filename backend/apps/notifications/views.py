import json
import threading
import time

from django.conf import settings
from django.http import HttpResponse, StreamingHttpResponse
from django.utils import timezone
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import AccessToken
from rest_framework import mixins, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ["id", "kind", "title", "body", "link", "booking", "read_at", "created_at"]


class NotificationViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = NotificationSerializer

    def get_queryset(self):
        return Notification.objects.filter(user=self.request.user)[:60]

    def list(self, request):
        qs = self.get_queryset()
        unread = Notification.objects.filter(user=request.user, read_at__isnull=True).count()
        return Response({"unread": unread, "items": self.get_serializer(qs, many=True).data})

    @action(detail=True, methods=["post"])
    def read(self, request, pk=None):
        Notification.objects.filter(user=request.user, pk=pk, read_at__isnull=True).update(read_at=timezone.now())
        return Response({"ok": True})

    @action(detail=False, methods=["post"], url_path="read-all")
    def read_all(self, request):
        Notification.objects.filter(user=request.user, read_at__isnull=True).update(read_at=timezone.now())
        return Response({"ok": True})


# Each open stream occupies one server thread, so unlimited tabs would leave none for normal requests.
_stream_slots = threading.BoundedSemaphore(settings.MAX_LIVE_STREAMS)


class LiveStream:
    """Gives its slot back when the response closes, including when the browser left before it started."""

    def __init__(self, events, slots):
        self.events, self.slots, self.closed = events, slots, False

    def __iter__(self):
        return self.events

    def close(self):
        if not self.closed:
            self.closed = True
            self.events.close()
            self.slots.release()


def stream(request):
    """
    Server-Sent Events: pushes each new notification to the browser the moment it is written, so
    approvals, auto-releases and reminders appear instantly instead of on the next poll.
    EventSource can't send headers, so the (short-lived) access token rides in the query string.
    """
    try:
        user_id = AccessToken(request.GET.get("token", ""))["user_id"]
    except (TokenError, KeyError):
        return HttpResponse(status=401)

    # When full, the browser retries shortly and the bell still updates through its regular refresh.
    slots = _stream_slots
    if not slots.acquire(blocking=False):
        return HttpResponse(status=503)

    try:
        last_id = Notification.objects.filter(user_id=user_id).order_by("-id").values_list("id", flat=True).first() or 0
    except Exception:
        slots.release()
        raise

    def events():
        nonlocal last_id
        yield "retry: 4000\n\n"
        started = time.monotonic()
        beat = 0.0
        # each connection lives ~5 minutes, then the browser transparently reconnects
        while time.monotonic() - started < 300:
            fresh = list(Notification.objects.filter(user_id=user_id, id__gt=last_id).order_by("id")[:20])
            for n in fresh:
                last_id = n.id
                yield f"event: notification\ndata: {json.dumps(NotificationSerializer(n).data, default=str)}\n\n"
            if time.monotonic() - beat > 15:
                beat = time.monotonic()
                yield ": keep-alive\n\n"
            time.sleep(2)

    resp = StreamingHttpResponse(LiveStream(events(), slots), content_type="text/event-stream")
    resp["Cache-Control"] = "no-cache"
    resp["X-Accel-Buffering"] = "no"
    return resp
