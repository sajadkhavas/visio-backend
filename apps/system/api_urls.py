from django.urls import path

from .api_views import ApiStatusView

urlpatterns = [path("system/status/", ApiStatusView.as_view(), name="api-status")]
