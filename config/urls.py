from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

from apps.system.views import health, readiness

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health, name="health"),
    path("ready/", readiness, name="readiness"),
    path("api/v1/schema/", SpectacularAPIView.as_view(), name="openapi-schema"),
    path("api/v1/", include("apps.system.api_urls")),
]
