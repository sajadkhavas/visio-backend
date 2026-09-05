from django.urls import path

from .api_views import OrderCancelView, OrderCollectionView, OrderDetailView

urlpatterns = [
    path("orders/", OrderCollectionView.as_view(), name="orders-collection"),
    path("orders/<uuid:public_id>/", OrderDetailView.as_view(), name="orders-detail"),
    path(
        "orders/<uuid:public_id>/cancel/",
        OrderCancelView.as_view(),
        name="orders-cancel",
    ),
]
