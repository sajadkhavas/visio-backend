from django.urls import path

from .api_views import ContentDetailView, ContentListView

urlpatterns = [
    path("content/", ContentListView.as_view(), name="content-list"),
    path(
        "content/<str:kind>/<slug:slug>/",
        ContentDetailView.as_view(),
        name="content-detail",
    ),
]
