from datetime import datetime, time, timedelta

from django.utils import timezone

from apps.accounts.models import Department, Role, User
from apps.catalogue.models import Custodian, Resource, ResourceType
from apps.rules.models import AvailabilityRule


def at(days, hour, minute=0):
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(timezone.localdate() + timedelta(days=days), time(hour, minute)), tz)


def make_user(username="u", role=Role.STUDENT, dept=None):
    return User.objects.create_user(username=username, password="x", role=role, department=dept)


def make_campus(requires_checkin=True):
    dept = Department.objects.create(code="CSE", name="CSE")
    rtype = ResourceType.objects.create(name="Laboratory", requires_checkin=requires_checkin)
    AvailabilityRule.objects.create(
        resource_type=rtype, weekdays=[0, 1, 2, 3, 4, 5, 6], open_time=time(6), close_time=time(23),
        min_duration_minutes=30, max_duration_minutes=240, min_lead_minutes=0, max_advance_days=60,
    )
    lab = Resource.objects.create(type=rtype, code="LAB-1", name="AI Lab", capacity=40, department=dept)
    custodian = make_user("custodian", Role.CUSTODIAN, dept)
    Custodian.objects.create(resource=lab, user=custodian, is_primary=True)
    return dept, rtype, lab, custodian
