import os

from django.core.exceptions import ImproperlyConfigured

from .base import *

SECRET_KEY = required_env("DJANGO_SECRET_KEY")
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must contain at least 50 characters.")

ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured("DJANGO_ALLOWED_HOSTS must contain at least one host.")

DATABASES = {
    "default": postgres_database(
        require_credentials=True,
        sslmode=os.getenv("POSTGRES_SSLMODE", "require"),
    )
}

if PAYMENTS_ENABLED:
    if PAYMENT_PROVIDER != "zarinpal":
        raise ImproperlyConfigured("PAYMENT_PROVIDER must be zarinpal when payments are enabled.")
    if not ZARINPAL_MERCHANT_ID:
        raise ImproperlyConfigured("ZARINPAL_MERCHANT_ID is required when payments are enabled.")
    if not PAYMENT_CALLBACK_URL.startswith("https://"):
        raise ImproperlyConfigured("PAYMENT_CALLBACK_URL must be an absolute HTTPS URL.")
    if ZARINPAL_SANDBOX:
        raise ImproperlyConfigured("ZARINPAL_SANDBOX cannot be enabled in production.")

DEBUG = False
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(os.getenv("DJANGO_SECURE_HSTS_SECONDS", "31536000"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("DJANGO_SECURE_HSTS_PRELOAD", False)
X_FRAME_OPTIONS = "DENY"
