"""
BookMyCampus — Django settings.

Configuration is read from environment variables (see .env.example). The only
hard runtime dependency for booking correctness is PostgreSQL: double-booking
is prevented by an exclusion constraint, not by application locks. Redis is
used purely as the Celery broker for background sweeps.
"""
import os
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env(name, default=None):
    return os.environ.get(name, default)


def env_bool(name, default=False):
    return str(env(name, default)).lower() in ("1", "true", "yes", "on")


SECRET_KEY = env("DJANGO_SECRET_KEY", "dev-insecure-change-me")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = [h.strip() for h in env("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",")]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.postgres",
    "rest_framework",
    "django_filters",
    "corsheaders",
    "apps.accounts",
    "apps.catalogue",
    "apps.rules",
    "apps.timetable",
    "apps.bookings",
    "apps.approvals",
    "apps.maintenance",
    "apps.consumables",
    "apps.analytics",
    "apps.notifications",
]

MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", "bookmycampus"),
        "USER": env("POSTGRES_USER", "bmc"),
        "PASSWORD": env("POSTGRES_PASSWORD", "bmc_dev_password"),
        "HOST": env("POSTGRES_HOST", "localhost"),
        "PORT": env("POSTGRES_PORT", "5433"),
        "CONN_MAX_AGE": 0,
    }
}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", "Asia/Kolkata")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_PAGINATION_CLASS": None,
    "EXCEPTION_HANDLER": "apps.bookings.exceptions.exception_handler",
}

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(hours=8),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
}

CORS_ALLOWED_ORIGINS = [
    o.strip() for o in env("CORS_ALLOWED_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")
]

# Console in dev. For real delivery set EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
# plus EMAIL_HOST / EMAIL_PORT / EMAIL_HOST_USER / EMAIL_HOST_PASSWORD (e.g. a Gmail app password).
EMAIL_BACKEND = env("EMAIL_BACKEND", "django.core.mail.backends.console.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", "localhost")
EMAIL_PORT = int(env("EMAIL_PORT", "587"))
EMAIL_HOST_USER = env("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
EMAIL_TIMEOUT = 10
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", "BookMyCampus <no-reply@bookmycampus.local>")

# Public base URL of the SPA, used inside QR codes and notification links.
FRONTEND_URL = env("FRONTEND_URL", "http://localhost:5173")

# P13 timetable feed. When set, the refresh task pulls the published timetable from here.
TIMETABLE_SOURCE_URL = env("TIMETABLE_SOURCE_URL", "")

# --- Celery (background sweeps only; booking correctness never depends on it) ---
CELERY_BROKER_URL = env("REDIS_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = None
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULE = {
    "sweep": {"task": "apps.bookings.tasks.sweep", "schedule": 60.0},
    "utilisation-snapshot": {"task": "apps.analytics.tasks.nightly_snapshot", "schedule": 3600.0},
    "timetable-refresh": {"task": "apps.timetable.tasks.refresh_timetable", "schedule": 900.0},
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

# Password given to the seeded demo personas (local development only).
DEMO_PASSWORD = env("DEMO_PASSWORD", "campus123")

# Shared secret P13 sends in X-Timetable-Token when it republishes the timetable.
TIMETABLE_WEBHOOK_TOKEN = env("TIMETABLE_WEBHOOK_TOKEN", "")

# Run the auto-release / reminder sweeper inside `runserver` (no extra terminal needed in dev).
AUTO_SWEEP = env_bool("AUTO_SWEEP", DEBUG)
AUTO_SWEEP_INTERVAL = int(env("AUTO_SWEEP_INTERVAL", "30"))
