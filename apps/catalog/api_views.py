from functools import reduce
from operator import or_

from django.db.models import Prefetch, Q, QuerySet
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny

from .models import (
    Brand,
    Category,
    Product,
    ProductBadge,
    ProductMedia,
    ProductOption,
    ProductOptionValue,
    ProductVariant,
    ProductVariantOption,
)
from .pagination import CatalogPagination
from .serializers import BrandSerializer, CategorySerializer, ProductSerializer

PRODUCT_QUERY_PARAMETERS = {
    "brand",
    "category",
    "material",
    "shape",
    "color",
    "sort",
    "page",
    "page_size",
}


def public_product_queryset() -> QuerySet[Product]:
    active_media = ProductMedia.objects.filter(is_active=True).order_by("position", "id")
    active_values = ProductOptionValue.objects.filter(is_active=True).order_by("position", "id")
    options = ProductOption.objects.order_by("position", "id").prefetch_related(
        Prefetch("values", queryset=active_values)
    )
    selections = ProductVariantOption.objects.select_related("option", "value").order_by("id")
    active_variants = (
        ProductVariant.objects.filter(is_active=True)
        .order_by("sort_order", "id")
        .prefetch_related(
            Prefetch("option_selections", queryset=selections),
            Prefetch("media", queryset=active_media),
        )
    )
    badges = ProductBadge.objects.filter(is_active=True).order_by("position", "id")

    return (
        Product.objects.filter(
            status=Product.Status.PUBLISHED,
            published_at__isnull=False,
            published_at__lte=timezone.now(),
            brand__is_active=True,
            category__is_active=True,
            media__is_active=True,
            media__variant__isnull=True,
        )
        .exclude(media__file="")
        .select_related("brand", "category")
        .prefetch_related(
            Prefetch("media", queryset=active_media),
            Prefetch("options", queryset=options),
            Prefetch("variants", queryset=active_variants),
            Prefetch("badges", queryset=badges),
        )
        .distinct()
    )


def parse_csv(value: str | None, *, field: str) -> list[str]:
    if value is None:
        return []
    items = list(dict.fromkeys(item.strip() for item in value.split(",") if item.strip()))
    if not items:
        raise ValidationError({field: "At least one non-empty value is required."})
    if len(items) > 20:
        raise ValidationError({field: "At most 20 values may be supplied."})
    return items


def reject_unknown_parameters(query_params: object) -> None:
    keys = set(query_params.keys())  # type: ignore[attr-defined]
    unknown = sorted(keys - PRODUCT_QUERY_PARAMETERS)
    if unknown:
        raise ValidationError({"query": f"Unsupported query parameter(s): {', '.join(unknown)}"})


def validated_catalog_queryset(query_params: object) -> QuerySet[Product]:
    reject_unknown_parameters(query_params)
    queryset = public_product_queryset()

    brands = parse_csv(query_params.get("brand"), field="brand")  # type: ignore[attr-defined]
    if brands:
        brand_predicates = [Q(brand__name__iexact=name) for name in brands]
        known = Brand.objects.filter(
            is_active=True,
            name__in=Brand.objects.filter(is_active=True).values("name"),
        )
        for brand_name in brands:
            if not known.filter(name__iexact=brand_name).exists():
                raise ValidationError({"brand": f"Unknown active brand: {brand_name}"})
        queryset = queryset.filter(reduce(or_, brand_predicates))

    category = query_params.get("category")  # type: ignore[attr-defined]
    if category:
        if not Category.objects.filter(slug=category, is_active=True).exists():
            raise ValidationError({"category": "Unknown active category."})
        queryset = queryset.filter(category__slug=category)

    materials = parse_csv(query_params.get("material"), field="material")  # type: ignore[attr-defined]
    if materials:
        known_materials = set(
            public_product_queryset()
            .filter(material__in=materials)
            .values_list("material", flat=True)
            .distinct()
        )
        missing = [value for value in materials if value not in known_materials]
        if missing:
            raise ValidationError({"material": f"Unknown material: {missing[0]}"})
        queryset = queryset.filter(material__in=materials)

    for field in ("shape", "color"):
        value = query_params.get(field)  # type: ignore[attr-defined]
        if value:
            if not public_product_queryset().filter(**{field: value}).exists():
                raise ValidationError({field: f"Unknown {field}."})
            queryset = queryset.filter(**{field: value})

    sort = query_params.get("sort", "default")  # type: ignore[attr-defined]
    if sort == "default":
        return queryset.order_by("sort_order", "name", "id")
    if sort == "name-asc":
        return queryset.order_by("name", "id")
    if sort == "name-desc":
        return queryset.order_by("-name", "id")
    raise ValidationError({"sort": "Allowed values: default, name-asc, name-desc."})


class BrandListView(ListAPIView):
    serializer_class = BrandSerializer
    permission_classes = (AllowAny,)
    authentication_classes: tuple[()] = ()
    pagination_class = None

    def get_queryset(self) -> QuerySet[Brand]:
        return Brand.objects.filter(is_active=True).order_by("sort_order", "name", "id")


class CategoryListView(ListAPIView):
    serializer_class = CategorySerializer
    permission_classes = (AllowAny,)
    authentication_classes: tuple[()] = ()
    pagination_class = None

    def get_queryset(self) -> QuerySet[Category]:
        return (
            Category.objects.filter(is_active=True)
            .select_related("parent")
            .order_by("sort_order", "name", "id")
        )


@extend_schema(
    parameters=[
        OpenApiParameter("brand", str, description="Comma-separated brand display names."),
        OpenApiParameter("category", str, description="Category slug."),
        OpenApiParameter("material", str, description="Comma-separated material values."),
        OpenApiParameter("shape", str, description="Exact shape value."),
        OpenApiParameter("color", str, description="Exact color value."),
        OpenApiParameter("sort", str, enum=["default", "name-asc", "name-desc"]),
        OpenApiParameter("page", int),
        OpenApiParameter("page_size", int, description="Maximum 48."),
    ]
)
class ProductListView(ListAPIView):
    serializer_class = ProductSerializer
    permission_classes = (AllowAny,)
    authentication_classes: tuple[()] = ()
    pagination_class = CatalogPagination

    def get_queryset(self) -> QuerySet[Product]:
        return validated_catalog_queryset(self.request.query_params)


class ProductDetailView(RetrieveAPIView):
    serializer_class = ProductSerializer
    permission_classes = (AllowAny,)
    authentication_classes: tuple[()] = ()
    lookup_field = "slug"
    lookup_url_kwarg = "slug"

    def get_queryset(self) -> QuerySet[Product]:
        return public_product_queryset()
