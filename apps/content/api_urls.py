from django.urls import path

from .api_views import (
    ContactMessageCreateView,
    ContentDetailView,
    ContentListView,
    HomepageView,
    SiteConfigurationView,
)

urlpatterns = [
    path("content/", ContentListView.as_view(), name="content-list"),
    path(
        "content/<str:kind>/<slug:slug>/",
        ContentDetailView.as_view(),
        name="content-detail",
    ),
    path("site/config/", SiteConfigurationView.as_view(), name="site-config"),
    path("site/home/", HomepageView.as_view(), name="site-home"),
    path("contact/messages/", ContactMessageCreateView.as_view(), name="contact-message-create"),
]
