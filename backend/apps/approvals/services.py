from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.accounts.models import Role, User
from apps.bookings.exceptions import BookingError
from apps.notifications.models import Notification
from apps.notifications.services import notify, notify_many

from .models import Approval, ApprovalWorkflow


def resolve_workflow(resource, user):
    """Highest-priority active workflow for this resource type whose roles include the requester."""
    candidates = ApprovalWorkflow.objects.filter(resource_type_id=resource.type_id, is_active=True).filter(
        Q(requester_roles=[]) | Q(requester_roles__contains=[user.role])
    )
    wf = candidates.order_by("-priority").prefetch_related("steps").first()
    if wf and wf.steps.exists():
        return wf
    return None


def approvers_for(resource, approver_role):
    if approver_role == Role.CUSTODIAN:
        return list(resource.custodians.all())
    if approver_role == Role.DEPT_HEAD:
        dept = resource.department
        return [dept.head] if dept and dept.head else list(User.objects.filter(role=Role.DEPT_HEAD, department=dept))
    return list(User.objects.filter(role__in=[Role.FACILITY_MANAGER]))


def can_decide(user, approval):
    if user.is_superuser or user.role == Role.ADMIN:
        return True
    resource = approval.booking.resource
    role = approval.approver_role
    if role == Role.CUSTODIAN:
        return resource.custodians.filter(pk=user.pk).exists()
    if role == Role.DEPT_HEAD:
        return user.role == Role.DEPT_HEAD and resource.department_id and user.department_id == resource.department_id
    if role == Role.FACILITY_MANAGER:
        return user.role == Role.FACILITY_MANAGER
    return False


def _activate(approval):
    approval.status = Approval.Status.PENDING
    approval.activated_at = timezone.now()
    approval.save(update_fields=["status", "activated_at"])
    b = approval.booking
    notify_many(
        approvers_for(b.resource, approval.approver_role),
        Notification.Kind.APPROVAL_REQUIRED,
        f"Approval needed: {b.resource.name}",
        f"{b.user} requests {timezone.localtime(b.start):%a %d %b %H:%M}–{timezone.localtime(b.end):%H:%M} "
        f"for “{b.title}”. Step: {approval.step_name}.",
        booking=b,
        link="/approvals",
    )


def attach_workflow(booking, workflow):
    steps = list(workflow.steps.all())
    approvals = [
        Approval(booking=booking, order=s.order, step_name=s.name, approver_role=s.approver_role) for s in steps
    ]
    Approval.objects.bulk_create(approvals)
    first = booking.approvals.order_by("order").first()
    _activate(first)
    notify(
        booking.user,
        Notification.Kind.APPROVAL_REQUIRED,
        f"Request sent: {booking.resource.name}",
        f"Your slot is held while it goes through {len(steps)} approval step(s): "
        + " → ".join(s.name for s in steps),
        booking=booking,
        link=f"/bookings/{booking.id}",
        email=False,
    )


def queue_for(user):
    """Pending approvals this user is entitled to decide."""
    qs = Approval.objects.filter(status=Approval.Status.PENDING, booking__status="pending").select_related(
        "booking__resource__type", "booking__resource__location", "booking__user__department"
    )
    if user.is_superuser or user.role == Role.ADMIN:
        return qs
    q = Q(pk__in=[])
    if user.custodied.exists():
        q |= Q(approver_role=Role.CUSTODIAN, booking__resource__in=user.custodied.all())
    if user.role == Role.DEPT_HEAD and user.department_id:
        q |= Q(approver_role=Role.DEPT_HEAD, booking__resource__department_id=user.department_id)
    if user.role == Role.FACILITY_MANAGER:
        q |= Q(approver_role=Role.FACILITY_MANAGER)
    return qs.filter(q)


def decide(booking, user, approve, comment="", series=False):
    from apps.bookings.models import Booking
    from apps.bookings.services import set_status

    targets = [booking]
    if series and booking.recurrence_id:
        targets = list(
            Booking.objects.filter(recurrence_id=booking.recurrence_id, status=Booking.Status.PENDING).order_by("period")
        )
    decided = 0
    for b in targets:
        with transaction.atomic():
            b = Booking.objects.select_for_update().get(pk=b.pk)
            if b.status != Booking.Status.PENDING:
                continue
            current = b.approvals.filter(status=Approval.Status.PENDING).order_by("order").first()
            if not current:
                continue
            if not can_decide(user, current):
                raise BookingError("forbidden", f"This step needs the {Role(current.approver_role).label}.", http_status=403)
            current.status = Approval.Status.APPROVED if approve else Approval.Status.REJECTED
            current.decided_by = user
            current.decided_at = timezone.now()
            current.comment = comment[:300]
            current.save()
            if not approve:
                set_status(b, Booking.Status.REJECTED, comment or f"Rejected at {current.step_name}")
                notify(
                    b.user, Notification.Kind.REJECTED, f"Not approved: {b.resource.name}",
                    f"{current.step_name} declined your request" + (f": “{comment}”" if comment else "."),
                    booking=b, link=f"/bookings/{b.id}",
                )
            else:
                nxt = b.approvals.filter(status=Approval.Status.WAITING).order_by("order").first()
                if nxt:
                    _activate(nxt)
                else:
                    b.status = Booking.Status.CONFIRMED
                    b.decided_at = timezone.now()
                    b.save(update_fields=["status", "decided_at"])
                    notify(
                        b.user, Notification.Kind.APPROVED, f"Approved: {b.resource.name}",
                        f"{timezone.localtime(b.start):%a %d %b %H:%M} is confirmed. Reference {b.reference}.",
                        booking=b, link=f"/bookings/{b.id}",
                    )
            decided += 1
    return decided
