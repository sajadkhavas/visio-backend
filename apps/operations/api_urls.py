from django.urls import path

from .api_views import OperationsSummaryView

app_name = "operations"

urlpatterns = [
    path("staff/operations/summary/", OperationsSummaryView.as_view(), name="summary"),
]
