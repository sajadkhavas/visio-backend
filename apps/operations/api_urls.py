from django.urls import path

from .api_views import OperationsSummaryView, StaffMeView

app_name = "operations"

urlpatterns = [
    path("staff/me/", StaffMeView.as_view(), name="staff-me"),
    path("staff/operations/summary/", OperationsSummaryView.as_view(), name="summary"),
]
