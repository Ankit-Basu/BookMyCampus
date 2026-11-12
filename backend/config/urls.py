from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView
from rest_framework.routers import DefaultRouter

from apps.accounts import views as accounts
from apps.analytics import views as analytics
from apps.approvals import views as approvals
from apps.bookings import views as bookings
from apps.catalogue import views as catalogue
from apps.consumables import views as consumables
from apps.maintenance import views as maintenance
from apps.notifications import views as notifications
from apps.rules import views as rules
from apps.timetable import views as timetable

router = DefaultRouter(trailing_slash=False)
router.register("resources", catalogue.ResourceViewSet, basename="resource")
router.register("resource-types", catalogue.ResourceTypeViewSet, basename="resource-type")
router.register("locations", catalogue.LocationViewSet)
router.register("bookings", bookings.BookingViewSet, basename="booking")
router.register("noshows", bookings.NoShowViewSet, basename="noshow")
router.register("availability-rules", rules.AvailabilityRuleViewSet)
router.register("blackouts", rules.BlackoutViewSet)
router.register("quotas", rules.QuotaViewSet)
router.register("workflows", approvals.WorkflowViewSet)
router.register("maintenance", maintenance.MaintenanceViewSet, basename="maintenance")
router.register("consumables", consumables.ConsumableViewSet, basename="consumable")
router.register("issuances", consumables.IssuanceViewSet, basename="issuance")
router.register("notifications", notifications.NotificationViewSet, basename="notification")
router.register("departments", accounts.DepartmentViewSet)
router.register("users", accounts.UserViewSet)

api = [
    path("auth/login", accounts.LoginView.as_view()),
    path("auth/register", accounts.RegisterView.as_view()),
    path("auth/departments", accounts.public_departments),
    path("auth/refresh", accounts.SafeRefreshView.as_view()),
    path("auth/demo-accounts", accounts.demo_accounts),
    path("me", accounts.MeView.as_view()),
    path("me/password", accounts.ChangePasswordView.as_view()),
    path("policy", rules.policy_view),
    path("approvals/queue", approvals.approval_queue),
    path("timetable/publish", timetable.publish),
    path("timetable/current", timetable.current),
    path("timetable/versions", timetable.versions),
    path("calendar/<uuid:token>.ics", bookings.calendar_feed),
    path("public/pass/<str:token>", bookings.public_pass),
    path("health", analytics.health),
    path("public/stats", analytics.public_stats),
    path("system/health", analytics.system_health),
    path("notifications/stream", notifications.stream),
    path("analytics/dashboard", analytics.dashboard),
    path("analytics/utilisation", analytics.utilisation),
    path("analytics/heatmap", analytics.heatmap),
    path("analytics/noshows", analytics.noshows),
    path("analytics/demand", analytics.demand),
    path("analytics/approvals", analytics.approvals),
    path("analytics/downtime", analytics.downtime),
    path("analytics/quotas", analytics.quotas),
    path("ai/", include("apps.ai_assistant.urls")),
    path("", include(router.urls)),
]

urlpatterns = [
    path("", RedirectView.as_view(url=settings.FRONTEND_URL, permanent=False)),
    path("django-admin/", admin.site.urls),
    path("api/", include(api)),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
