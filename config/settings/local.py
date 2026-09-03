import os

from .base import *

SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "visio-local-development-only-secret-key")
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", ["localhost", "127.0.0.1"])
DATABASES = {"default": postgres_database(require_credentials=False)}
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")
