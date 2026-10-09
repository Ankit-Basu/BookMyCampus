from django.conf import settings
from django.utils import timezone
from rest_framework import generics, viewsets
from rest_framework.decorators import action, api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from .models import Department, Role, User
from .permissions import IsManager, ReadOnlyOrPolicyAdmin
from .serializers import DepartmentSerializer, LoginSerializer, UserSerializer


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


class UserViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = User.objects.select_related("department").order_by("first_name")
    serializer_class = UserSerializer
    permission_classes = [IsManager]
    filterset_fields = ["role", "department"]
    search_fields = ["username", "first_name", "last_name", "email"]

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
