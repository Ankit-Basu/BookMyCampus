from django.db import IntegrityError
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

EXCLUSION_VIOLATION = "23P01"
DEADLOCK_DETECTED = "40P01"


def is_exclusion_violation(exc: IntegrityError) -> bool:
    """True when PostgreSQL refused a row because of an EXCLUDE constraint (an overlap)."""
    cause = exc.__cause__
    return getattr(cause, "sqlstate", None) == EXCLUSION_VIOLATION


def is_deadlock(exc) -> bool:
    return getattr(exc.__cause__, "sqlstate", None) == DEADLOCK_DETECTED


class BookingError(Exception):
    """A domain error with a stable machine-readable code the frontend can react to."""

    http_status = status.HTTP_400_BAD_REQUEST

    def __init__(self, code, message, details=None, http_status=None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}
        if http_status:
            self.http_status = http_status


class SlotConflict(BookingError):
    http_status = status.HTTP_409_CONFLICT

    def __init__(self, message="That slot was just taken.", details=None):
        super().__init__("slot_conflict", message, details)


class RuleViolation(BookingError):
    http_status = status.HTTP_422_UNPROCESSABLE_ENTITY


def exception_handler(exc, context):
    if isinstance(exc, BookingError):
        return Response({"error": exc.code, "message": exc.message, "details": exc.details}, status=exc.http_status)
    return drf_exception_handler(exc, context)
