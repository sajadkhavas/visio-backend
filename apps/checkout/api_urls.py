from django.urls import path

from .api_views import (
    CheckoutCancelView,
    CheckoutCreateView,
    CheckoutFinalizeView,
    CurrentCheckoutView,
    ShippingOptionsView,
)

urlpatterns = [
    path(
        "checkout/shipping-options/",
        ShippingOptionsView.as_view(),
        name="checkout-shipping-options",
    ),
    path("checkout/current/", CurrentCheckoutView.as_view(), name="checkout-current"),
    path("checkout/sessions/", CheckoutCreateView.as_view(), name="checkout-create"),
    path(
        "checkout/sessions/<uuid:checkout_id>/finalize/",
        CheckoutFinalizeView.as_view(),
        name="checkout-finalize",
    ),
    path(
        "checkout/sessions/<uuid:checkout_id>/cancel/",
        CheckoutCancelView.as_view(),
        name="checkout-cancel",
    ),
]
