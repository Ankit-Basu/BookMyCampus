import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class Department(models.Model):
    code = models.CharField(max_length=16, unique=True)
    name = models.CharField(max_length=120)
    head = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="headed_departments"
    )

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return f"{self.code} · {self.name}"


class Role(models.TextChoices):
    STUDENT = "student", "Student"
    FACULTY = "faculty", "Faculty"
    STAFF = "staff", "Staff"
    CUSTODIAN = "custodian", "Resource Custodian"
    DEPT_HEAD = "dept_head", "Department Head"
    FACILITY_MANAGER = "facility_manager", "Facility Manager"
    ADMIN = "admin", "Administrator"


# Roles allowed to manage the system beyond their own bookings.
MANAGER_ROLES = {Role.CUSTODIAN, Role.DEPT_HEAD, Role.FACILITY_MANAGER, Role.ADMIN}
# Roles allowed to create recurring bookings / book on behalf of a class.
RECURRING_ROLES = {Role.FACULTY, Role.STAFF, Role.CUSTODIAN, Role.DEPT_HEAD, Role.FACILITY_MANAGER, Role.ADMIN}


class User(AbstractUser):
    role = models.CharField(max_length=24, choices=Role.choices, default=Role.STUDENT)
    department = models.ForeignKey(Department, null=True, blank=True, on_delete=models.SET_NULL, related_name="members")
    phone = models.CharField(max_length=20, blank=True)
    # Secret for the personal iCal feed URL; rotate to revoke a leaked feed.
    calendar_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    # Progressive no-show restriction: while set and in the future, the user cannot book.
    restricted_until = models.DateTimeField(null=True, blank=True)
    restriction_reason = models.CharField(max_length=200, blank=True)

    @property
    def is_restricted(self):
        return bool(self.restricted_until and self.restricted_until > timezone.now())

    @property
    def is_manager(self):
        return self.role in MANAGER_ROLES or self.is_superuser

    @property
    def can_book_recurring(self):
        return self.role in RECURRING_ROLES or self.is_superuser

    def __str__(self):
        return self.get_full_name() or self.username


class DepartmentNotice(models.Model):
    """A message an HOD sends to everyone in their department, e.g. "Lab 501 is closed tomorrow"."""

    class Audience(models.TextChoices):
        EVERYONE = "everyone", "Everyone"
        FACULTY = "faculty", "Faculty"
        STUDENTS = "students", "Students"

    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="notices")
    author = models.ForeignKey("accounts.User", null=True, on_delete=models.SET_NULL, related_name="+")
    audience = models.CharField(max_length=10, choices=Audience.choices, default=Audience.EVERYONE)
    title = models.CharField(max_length=120)
    body = models.CharField(max_length=500, blank=True)
    recipients = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
