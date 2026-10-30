import os
import sys
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent
TESTING = len(sys.argv) > 1 and sys.argv[1] == "test"
# `manage.py runserver` is the developer's own computer: plain http, no HTTPS. Production runs under gunicorn,
# so it is never treated as development unless DJANGO_DEBUG=1 is set on purpose.
RUNSERVER = len(sys.argv) > 1 and sys.argv[1] == "runserver"

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-change-me")
DEBUG = os.environ.get("DJANGO_DEBUG", "1" if RUNSERVER else "0") == "1"
ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1").split(",") if h]
if RUNSERVER and DEBUG:
    ALLOWED_HOSTS = ["*"]  # development only: lets a phone on the same Wi-Fi reach http://<computer-ip>:8000
CSRF_TRUSTED_ORIGINS = [o for o in os.environ.get("DJANGO_CSRF_ORIGINS", "").split(",") if o]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "rest_framework.authtoken",
    "corsheaders",
    "core",
    "accounts",
    "academics",
    "questions",
    "exams",
    "notifications",
    "analytics",
    "gamification",
    "guardians",
    "proctoring",
    "controlroom",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "controlroom.middleware.MaintenanceMiddleware",  # site-wide maintenance switch; after CORS so its 503 reaches the web app
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "controlroom.middleware.OwnerOnlyMiddleware",  # while the site is in maintenance, only the owner may open /django-admin/
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

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
            ]
        },
    }
]

DATABASES = {
    "default": dj_database_url.config(
        default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}", conn_max_age=60
    )
}

if os.environ.get("REDIS_URL"):
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": os.environ["REDIS_URL"],
        }
    }
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

AUTH_USER_MODEL = "accounts.User"

# The first hasher is the preferred one. The "initial" hasher is lighter and is used
# only for the starting password (the index number) of bulk-uploaded students, so that
# 500 accounts can be created in under a minute (acceptance test). Django re-hashes with
# the preferred hasher automatically on the first successful login, and the student is
# forced to choose a new password at that point anyway.
PASSWORD_HASHERS = [
    "accounts.hashers.StrongPasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",  # older hashes still verify and are upgraded
    "accounts.hashers.InitialPasswordHasher",
]

if TESTING:  # tests create many users; the real (slow) hashers would make the suite take minutes
    PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher", "accounts.hashers.InitialPasswordHasher"]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en"
TIME_ZONE = "Africa/Dar_es_Salaam"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}
MEDIA_URL = "media/"
MEDIA_ROOT = Path(os.environ.get("MEDIA_ROOT", BASE_DIR / "media"))

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "core.pagination.OptionalPagination",  # pages only when ?page= is sent
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.TokenAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
        "accounts.permissions.NotForcedPasswordChange",
    ],
    "DEFAULT_THROTTLE_CLASSES": ["rest_framework.throttling.ScopedRateThrottle"],
    # Load testing from ONE computer needs a higher limit: set LOGIN_THROTTLE_RATE=100000/min on the test server only.
    "DEFAULT_THROTTLE_RATES": {"login": os.environ.get("LOGIN_THROTTLE_RATE", "20/min")},
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    # PDF / Excel / CSV downloads must not be refused because of a browser's Accept header.
    "DEFAULT_CONTENT_NEGOTIATION_CLASS": "core.negotiation.IgnoreAcceptNegotiation",
}

# Web Push (NOT-02). Optional: leave empty and in-app notifications still work.
# Generate keys with:  pip install pywebpush && vapid --gen   (or any VAPID key tool)
# Secret that encrypts parents' names and phone numbers. Not stored in the database. See guardians/crypto.py.
GUARDIAN_KEY = os.environ.get("GUARDIAN_KEY", "")

# Control room (/controlroom/, maintenance mode + God's Eye). Comma-separated user names of the owner(s): only they can get in while the
# site is in maintenance. Empty = any superuser. Optional CONTROLROOM_EXEMPT_PREFIXES = paths that stay up (e.g. ["/api/sms/"] for the SMS phone).
CONTROLROOM_OWNERS = os.environ.get("CONTROLROOM_OWNERS", "")

# Anti-cheat: proximity monitoring during exams (see proctoring/ and the Privacy policy section on location).
PROCTORING_ENABLED = os.environ.get("PROCTORING_ENABLED", "1") == "1"
PROXIMITY_ALERT_METERS = float(os.environ.get("PROXIMITY_ALERT_METERS", "20"))   # alert when two students are closer than this
LOCATION_STALE_SECONDS = int(os.environ.get("LOCATION_STALE_SECONDS", "45"))      # a position older than this is not used
PROXIMITY_CLEAR_SECONDS = int(os.environ.get("PROXIMITY_CLEAR_SECONDS", "60"))    # an alert ends after this long apart
LOCATION_MAX_ACCURACY = float(os.environ.get("LOCATION_MAX_ACCURACY", "100"))     # fixes worse than this (metres) are shown but not compared
# Place names (street, district, country) for administrators. "" switches it off. Point it at your own Nominatim server to keep all data in-house.
GEOCODER_URL = os.environ.get("GEOCODER_URL", "https://nominatim.openstreetmap.org/reverse")
GEOCODER_USER_AGENT = os.environ.get("GEOCODER_USER_AGENT", "AmaniExams/1.0 (school exam system; contact: " + os.environ.get("VAPID_CONTACT_EMAIL", "admin@example.com") + ")")
LEGAL_VERSION = "2026-10-29b"  # bump when the Terms or Privacy policy change; shown to students and stored with each acceptance
VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_CONTACT_EMAIL = os.environ.get("VAPID_CONTACT_EMAIL", "admin@example.com")

# Production: set CORS_ORIGINS to the address of the web app (https://exams.example.com), nothing else is allowed.
CORS_ALLOWED_ORIGINS = [o for o in os.environ.get("CORS_ORIGINS", "").split(",") if o]
if RUNSERVER and DEBUG and not CORS_ALLOWED_ORIGINS:
    CORS_ALLOW_ALL_ORIGINS = True  # development only: the web app on localhost:3000, or on a phone via the computer's IP

if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    # Not during `manage.py test`: the test client speaks plain http and would get 301s.
    SECURE_SSL_REDIRECT = os.environ.get("DJANGO_SSL_REDIRECT", "1") == "1" and not TESTING
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 31536000
