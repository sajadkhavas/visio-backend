from django.urls import path

from .api_views import PaymentCollectionView, PaymentDetailView, ZarinPalCallbackView

app_name = "payments"

urlpatterns = [
    path("payments/", PaymentCollectionView.as_view(), name="collection"),
    path("payments/<uuid:attempt_id>/", PaymentDetailView.as_view(), name="detail"),
    path(
        "payments/zarinpal/callback/",
        ZarinPalCallbackView.as_view(),
        name="zarinpal-callback",
    ),
]
