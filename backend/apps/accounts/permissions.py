from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Role


class IsManager(BasePermission):
    """Custodians, department heads, facility managers, admins."""

    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and request.user.is_manager)


class IsPolicyAdmin(BasePermission):
    """Facility managers and administrators — campus-wide configuration."""

    def has_permission(self, request, view):
        u = request.user
        return bool(u and u.is_authenticated and (u.is_superuser or u.role in (Role.FACILITY_MANAGER, Role.ADMIN)))


class ReadOnlyOrManager(BasePermission):
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return request.method in SAFE_METHODS or request.user.is_manager


class ReadOnlyOrPolicyAdmin(BasePermission):
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return request.method in SAFE_METHODS or IsPolicyAdmin().has_permission(request, view)
