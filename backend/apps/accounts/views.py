from django.conf import settings
from django.utils import timezone
from datetime import timedelta

from django.db.models import Count, Q
from rest_framework import generics, mixins, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .models import Department, Role, User
from .permissions import IsManager, IsPolicyAdmin, ReadOnlyOrPolicyAdmin
from .serializers import AdminUserSerializer, DepartmentSerializer, LoginSerializer, UserSerializer


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer


class MeView(generics.RetrieveUpdateAPIView):
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user


class DepartmentViewSet(viewsets.ModelViewSet):
    queryset = Department.objects.select_related("head")
    serializer_class = DepartmentSerializer
    permission_classes = [ReadOnlyOrPolicyAdmin]


class UserViewSet(mixins.CreateModelMixin, mixins.UpdateModelMixin, viewsets.ReadOnlyModelViewSet):
    """
    People directory. Every manager can search it; facility managers and admins can also create
    accounts, change role / department, reset passwords and (de)activate users.
    """

    queryset = User.objects.select_related("department").order_by("first_name")
    serializer_class = UserSerializer
    permission_classes = [IsManager]
    filterset_fields = ["role", "department", "is_active"]
    search_fields = ["username", "first_name", "last_name", "email"]

    def get_permissions(self):
        if self.action in ("create", "update", "partial_update"):
            return [IsPolicyAdmin()]
        return super().get_permissions()

    def get_serializer_class(self):
        if self.action in ("create", "update", "partial_update") or self.request.query_params.get("directory") == "1":
            return AdminUserSerializer
        return UserSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if self.request.query_params.get("directory") == "1" or self.action in ("update", "partial_update"):
            since = timezone.now() - timedelta(days=30)
            qs = qs.annotate(
                booking_count=Count("bookings", distinct=True),
                noshows_30d=Count("noshows", filter=Q(noshows__recorded_at__gte=since, noshows__waived=False), distinct=True),
            )
        return qs

    @action(detail=False)
    def restricted(self, request):
        qs = self.get_queryset().filter(restricted_until__gt=timezone.now())
        return Response(self.get_serializer(qs, many=True).data)

    @action(detail=True, methods=["post"], url_path="lift-restriction")
    def lift_restriction(self, request, pk=None):
        u = self.get_object()
        u.restricted_until = None
        u.restriction_reason = ""
        u.save(update_fields=["restricted_until", "restriction_reason"])
        return Response(self.get_serializer(u).data)


@api_view(["GET"])
@permission_classes([AllowAny])
def demo_accounts(request):
    """One-click personas on the login screen (only exposed while DEBUG is on)."""
    if not settings.DEBUG:
        return Response([])
    out = []
    for role in Role.values:
        u = User.objects.filter(role=role, username__startswith="demo.").order_by("id").first()
        if u:
            out.append({"username": u.username, "name": u.get_full_name(), "role": role, "role_label": Role(role).label, "password": settings.DEMO_PASSWORD})
    return Response(out)


class SafeRefreshView(TokenRefreshView):
    """Token refresh that answers 401 (not 500) when the token's user no longer exists."""

    def post(self, request, *args, **kwargs):
        try:
            return super().post(request, *args, **kwargs)
        except User.DoesNotExist:
            return Response({"error": "user_not_found", "message": "Please sign in again."}, status=401)
