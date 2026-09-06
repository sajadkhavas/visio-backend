import os
from urllib.parse import urlparse

from django.core.exceptions import ImproperlyConfigured

from .base import *

SECRET_KEY = required_env("DJANGO_SECRET_KEY")
if len(SECRET_KEY) < 50 or len(set(SECRET_KEY)) < 5 or SECRET_KEY.startswith("django-insecure-"):
    raise ImproperlyConfigured(
        "DJANGO_SECRET_KEY must be at least 50 characters, sufficiently diverse, and not insecure."
    )

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must contain at least one host.")
if any(host == "*" or "*" in host for host in ALLOWED_HOSTS):
    raise ImproperlyConfigured(
        "Wildcard DJANGO_ALLOWED_HOSTS entries are not allowed in production."
    )

POSTGRES_SSLMODE = os.getenv("POSTGRES_SSLMODE", "require").strip().lower()
if POSTGRES_SSLMODE in {"disable", "allow", "prefer"}:
    raise ImproperlyConfigured(
        "POSTGRES_SSLMODE must not permit plaintext or downgrade-capable "
        "database transport in production."
    )
DATABASES = {
    "default": postgres_database(
        require_credentials=True,
        sslmode=POSTGRES_SSLMODE,
    )
}

if PAYMENT_PROVIDER_TIMEOUT_SECONDS <= 0 or PAYMENT_PROVIDER_TIMEOUT_SECONDS > 30:
    raise ImproperlyConfigured("PAYMENT_PROVIDER_TIMEOUT_SECONDS must be within (0, 30].")

if PAYMENTS_ENABLED:
    if PAYMENT_PROVIDER != "zarinpal":
        raise ImproperlyConfigured("PAYMENT_PROVIDER must be zarinpal when payments are enabled.")
    if not ZARINPAL_MERCHANT_ID:
        raise ImproperlyConfigured("ZARINPAL_MERCHANT_ID is required when payments are enabled.")
    if not PAYMENT_CALLBACK_URL.startswith("https://"):
        raise ImproperlyConfigured("PAYMENT_CALLBACK_URL must be an absolute HTTPS URL.")
    if ZARINPAL_SANDBOX:
        raise ImproperlyConfigured("ZARINPAL_SANDBOX cannot be enabled in production.")

if EMAIL_TIMEOUT <= 0 or EMAIL_TIMEOUT > 30:
    raise ImproperlyConfigured("EMAIL_TIMEOUT must be within (0, 30] seconds in production.")

if NOTIFICATIONS_ENABLED:
    if NOTIFICATION_CHANNEL != "email":
        raise ImproperlyConfigured(
            "NOTIFICATION_CHANNEL must be email when notifications are enabled."
        )
    development_backends = {
        "django.core.mail.backends.console.EmailBackend",
        "django.core.mail.backends.locmem.EmailBackend",
        "django.core.mail.backends.dummy.EmailBackend",
        "django.core.mail.backends.filebased.EmailBackend",
    }
    if EMAIL_BACKEND in development_backends:
        raise ImproperlyConfigured("A production-capable EMAIL_BACKEND is required.")
    if not DEFAULT_FROM_EMAIL or DEFAULT_FROM_EMAIL == "webmaster@localhost":
        raise ImproperlyConfigured(
            "DEFAULT_FROM_EMAIL must be configured for production notifications."
        )
    if EMAIL_USE_TLS and EMAIL_USE_SSL:
        raise ImproperlyConfigured("EMAIL_USE_TLS and EMAIL_USE_SSL cannot both be enabled.")
    if EMAIL_BACKEND == "django.core.mail.backends.smtp.EmailBackend" and not EMAIL_HOST:
        raise ImproperlyConfigured("EMAIL_HOST is required for the SMTP email backend.")

DEBUG = False
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
for origin in CSRF_TRUSTED_ORIGINS:
    parsed = urlparse(origin)
    if parsed.scheme != "https" or not parsed.netloc or "*" in parsed.netloc:
        raise ImproperlyConfigured(
            "DJANGO_CSRF_TRUSTED_ORIGINS must contain explicit absolute HTTPS origins."
        )

SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
if not SECURE_SSL_REDIRECT:
    raise ImproperlyConfigured("DJANGO_SECURE_SSL_REDIRECT must remain enabled in production.")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
if SECURE_HSTS_SECONDS <= 0:
    raise ImproperlyConfigured("DJANGO_SECURE_HSTS_SECONDS must be positive in production.")
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_SECURE_HSTS_PRELOAD", False)
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
