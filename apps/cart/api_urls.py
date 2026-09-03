from django.urls import path

from .api_views import (
    CartImportView,
    CartLineCreateView,
    CartLineDetailView,
    CartValidateView,
    CurrentCartView,
    WishlistItemView,
    WishlistView,
)

urlpatterns = [
    path("cart/", CurrentCartView.as_view(), name="cart-current"),
    path("cart/lines/", CartLineCreateView.as_view(), name="cart-line-create"),
    path(
        "cart/lines/<uuid:variant_id>/",
        CartLineDetailView.as_view(),
        name="cart-line-detail",
    ),
    path("cart/validate/", CartValidateView.as_view(), name="cart-validate"),
    path("cart/import/", CartImportView.as_view(), name="cart-import"),
    path("wishlist/", WishlistView.as_view(), name="wishlist-current"),
    path(
        "wishlist/<uuid:product_id>/",
        WishlistItemView.as_view(),
        name="wishlist-item",
    ),
]
