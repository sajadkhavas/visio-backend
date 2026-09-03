from django.urls import path

from .api_views import BrandListView, CategoryListView, ProductDetailView, ProductListView

app_name = "catalog"

urlpatterns = [
    path("catalog/brands/", BrandListView.as_view(), name="brand-list"),
    path("catalog/categories/", CategoryListView.as_view(), name="category-list"),
    path("catalog/products/", ProductListView.as_view(), name="product-list"),
    path("catalog/products/<slug:slug>/", ProductDetailView.as_view(), name="product-detail"),
]
