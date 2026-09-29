"""
Django settings for the Titans Windows CRM+ERP system.

Configuration is environment-driven (see .env.example) so the same codebase
runs safely in development and in production without code changes.
"""

from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(
    DEBUG=(bool, False),
)
# Read .env if present (it is git-ignored; see .env.example for the template)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("DJANGO_SECRET_KEY", default="django-insecure-dev-key-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# Render tells every web service its own public address. Trusting it here means
# the site works on its first deploy without anyone typing the address into two
# settings by hand — and forgetting one gives a "400 Bad Request" on every page
# or a "CSRF verification failed" on every sign-in. A custom domain is still
# added through ALLOWED_HOSTS and CSRF_TRUSTED_ORIGINS as before.
_render_host = env("RENDER_EXTERNAL_HOSTNAME", default="")
if _render_host:
    if _render_host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(_render_host)
    if f"https://{_render_host}" not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(f"https://{_render_host}")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    # Third-party
    "crispy_forms",
    "crispy_bootstrap5",
    "widget_tweaks",
    # Titans CRM apps
    "apps.accounts",
    "apps.crm",
]

MIDDLEWARE = [
    # First, so a health check is answered before anything checks who is asking.
    "titans_crm.health.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.accounts.middleware.ForcePasswordChange",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "titans_crm.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.crm.context_processors.navigation",
                "apps.crm.context_processors.storage",
                "apps.crm.context_processors.month_end",
                "apps.crm.context_processors.reminders",
            ],
        },
    },
]

WSGI_APPLICATION = "titans_crm.wsgi.application"

# ---------------------------------------------------------------------------
# Database
#
# Defaults to SQLite so the project runs immediately with zero setup.
# For production, set DATABASE_URL (see .env.example) to point at PostgreSQL,
# e.g. postgres://user:password@localhost:5432/titans_crm
# ---------------------------------------------------------------------------
_database_url = env("DATABASE_URL", default="") or f"sqlite:///{BASE_DIR / 'db.sqlite3'}"
DATABASES = {"default": env.db_url_config(_database_url)}

AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

AUTHENTICATION_BACKENDS = ["apps.accounts.backends.CaseInsensitiveModelBackend"]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "crm:dashboard"
LOGOUT_REDIRECT_URL = "accounts:login"

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("TIME_ZONE", default="Asia/Kolkata")
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
# Django 5.1 dropped the old STATICFILES_STORAGE setting, so storages are
# declared here. Compressed (not manifest) storage: whitenoise serves gzip/brotli
# without every page 500ing if collectstatic ever missed a file.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedStaticFilesStorage"},
}

# Uploaded documents — quotations, signed CAFs, production sheets, receipts —
# have to outlive a redeploy. On a host with no persistent disk, point these at
# any S3-compatible bucket (Cloudflare R2, Supabase Storage, Backblaze B2) and
# Django writes there instead of the local media/ folder. Leave unset and
# nothing changes.
AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="")
if AWS_STORAGE_BUCKET_NAME:
    STORAGES["default"] = {"BACKEND": "storages.backends.s3.S3Storage"}
    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID")
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY")
    AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default=None)
    AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default="auto")
    # R2 and B2 address a bucket as a subdomain; Supabase puts it in the path.
    # Pointing boto3 the wrong way makes every upload fail to resolve a host.
    AWS_S3_ADDRESSING_STYLE = env("AWS_S3_ADDRESSING_STYLE", default="virtual")
    # Signed links are how a private bucket hands a file to a signed-in person.
    # R2, B2, Supabase and S3 itself all speak version 4; naming it here stops
    # boto3 choosing an older scheme for a custom endpoint, which some refuse.
    AWS_S3_SIGNATURE_VERSION = env("AWS_S3_SIGNATURE_VERSION", default="s3v4")
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    # Links are signed and short-lived, so a bucket can stay private.
    AWS_QUERYSTRING_AUTH = True
    AWS_QUERYSTRING_EXPIRE = env.int("AWS_QUERYSTRING_EXPIRE", default=3600)

# How much room the bucket has, so the Super Admin is warned before it is full.
# 1000 is Supabase's free 1 GB; after upgrading, set STORAGE_LIMIT_MB on the host
# to the new size (100 GB is 100000). The warning starts at 80% and turns red at 95%.
STORAGE_LIMIT_MB = env.int("STORAGE_LIMIT_MB", default=1000)
STORAGE_WARN_PERCENT = env.int("STORAGE_WARN_PERCENT", default=80)
STORAGE_CRITICAL_PERCENT = env.int("STORAGE_CRITICAL_PERCENT", default=95)

# Texting the Super Admin a password-reset code. Without a provider the code is
# written to the server log instead (see apps/accounts/sms.py), which on a host
# like Render is readable only by whoever owns the hosting account.
SMS_PROVIDER = env("SMS_PROVIDER", default="")            # "fast2sms", or empty
FAST2SMS_API_KEY = env("FAST2SMS_API_KEY", default="")
FAST2SMS_URL = env("FAST2SMS_URL", default="https://www.fast2sms.com/dev/bulkV2")

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

CRISPY_ALLOWED_TEMPLATE_PACKS = "bootstrap5"
CRISPY_TEMPLATE_PACK = "bootstrap5"

MESSAGE_TAGS = {
    10: "secondary",  # DEBUG
}

SESSION_COOKIE_AGE = env.int("SESSION_COOKIE_AGE", default=60 * 60 * 10)  # 10 hours
SESSION_EXPIRE_AT_BROWSER_CLOSE = False

# Security hardening (relaxed automatically when DEBUG=True for local dev)
# Render (like most hosts) ends HTTPS at its proxy and forwards plain HTTP, so
# trust its X-Forwarded-Proto header or SECURE_SSL_REDIRECT would loop forever.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=not DEBUG)
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=not DEBUG)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=not DEBUG)
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
# Off by default: turning HSTS on before HTTPS definitely works everywhere locks
# browsers out of the site for the duration. Set it once the certificate is in
# place and the site has been used over HTTPS for a day or two.
SECURE_HSTS_SECONDS = env.int("SECURE_HSTS_SECONDS", default=0)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", default=False)
SECURE_HSTS_PRELOAD = env.bool("SECURE_HSTS_PRELOAD", default=False)

# File upload limits (site photos / drawings can be large)
DATA_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 20 * 1024 * 1024
# The largest single document anyone can upload. A scanned PDF or a drawing is
# well under this; a phone video is not, and would eat the storage bucket.
MAX_UPLOAD_MB = env.int("MAX_UPLOAD_MB", default=25)

# How often, at most, the calendar reminders (a late installation) are looked for.
REMINDER_CHECK_SECONDS = env.int("REMINDER_CHECK_SECONDS", default=600)

# ---------------------------------------------------------------------------
# Logging: errors always go to file so nothing is lost silently.
# ---------------------------------------------------------------------------
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{asctime} {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "titans_crm.log",
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 5,
            "formatter": "verbose",
        },
    },
    "root": {"handlers": ["console", "file"], "level": "INFO"},
}
