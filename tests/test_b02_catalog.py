from datetime import timedelta

import pytest
from apps.catalog.models import (
    Brand,
    Category,
    Product,
    ProductMedia,
    ProductOption,
    ProductOptionValue,
    ProductVariant,
    ProductVariantOption,
)
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, connection, transaction
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

pytestmark = pytest.mark.django_db

PRODUCTS_PATH = "/api/v1/catalog/products/"


def create_brand(name: str = "Ray-Ban", slug: str = "ray-ban", *, active: bool = True) -> Brand:
    return Brand.objects.create(name=name, slug=slug, is_active=active)


def create_category(
    name: str = "آفتابی مردانه",
    slug: str = "sun-men",
    *,
    active: bool = True,
) -> Category:
    return Category.objects.create(name=name, slug=slug, is_active=active)


def create_published_product(
    *,
    name: str = "Aviator",
    slug: str = "aviator",
    brand: Brand | None = None,
    category: Category | None = None,
    material: str = "تیتانیوم",
    shape: str = "گرد",
    color: str = "طلایی",
    published_at_offset: timedelta = timedelta(0),
    with_media: bool = True,
) -> Product:
    product = Product.objects.create(
        name=name,
        slug=slug,
        brand=brand or create_brand(),
        category=category or create_category(),
        status=Product.Status.PUBLISHED,
        published_at=timezone.now() + published_at_offset,
        material=material,
        shape=shape,
        color=color,
        lens_width_mm=52,
        bridge_width_mm=18,
        temple_length_mm=145,
        frame_width_mm=140,
    )
    if with_media:
        ProductMedia.objects.create(
            product=product,
            file=SimpleUploadedFile("front.jpg", b"catalog-media", content_type="image/jpeg"),
            alt=f"{name} front",
            width=1200,
            height=900,
            position=0,
        )
    return product


def test_public_product_payload_matches_frozen_frontend_and_keeps_b03_fail_closed() -> None:
    product = create_published_product()
    option = ProductOption.objects.create(product=product, key="color", label="رنگ", position=0)
    gold = ProductOptionValue.objects.create(
        option=option,
        value="gold",
        label="طلایی",
        position=0,
    )
    variant = ProductVariant.objects.create(
        product=product,
        sku="RB-AVIATOR-GOLD",
        is_default=True,
    )
    ProductVariantOption.objects.create(variant=variant, option=option, value=gold)

    response = Client().get(PRODUCTS_PATH)

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    item = payload["results"][0]
    assert item["id"] == str(product.id)
    assert item["slug"] == "aviator"
    assert item["brand"] == "Ray-Ban"
    assert item["category"] == "sun-men"
    assert item["source"] == "backend"
    assert item["authoritative"] is True
    assert item["priceContract"] == {
        "current": None,
        "compareAt": None,
        "authoritative": False,
        "source": "backend",
        "updatedAt": None,
    }
    assert item["price"] == 0
    assert item["availability"]["status"] == "unknown"
    assert item["availability"]["authoritative"] is False
    assert item["inStock"] is False
    assert item["defaultVariantId"] == str(variant.id)
    assert item["variants"][0]["options"] == {"color": "gold"}
    assert item["images"][0]["alt"] == "Aviator front"


def test_public_api_hides_draft_future_inactive_and_medialess_products() -> None:
    brand = create_brand()
    category = create_category()
    visible = create_published_product(brand=brand, category=category)

    Product.objects.create(
        name="Draft",
        slug="draft",
        brand=brand,
        category=category,
        status=Product.Status.DRAFT,
    )
    create_published_product(
        name="Future",
        slug="future",
        brand=brand,
        category=category,
        published_at_offset=timedelta(days=1),
    )
    create_published_product(
        name="No media",
        slug="no-media",
        brand=brand,
        category=category,
        with_media=False,
    )
    inactive_brand = create_brand("Inactive", "inactive", active=False)
    create_published_product(
        name="Inactive brand",
        slug="inactive-brand",
        brand=inactive_brand,
        category=category,
    )

    response = Client().get(PRODUCTS_PATH)

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["results"]] == [str(visible.id)]
    assert Client().get(f"{PRODUCTS_PATH}draft/").status_code == 404
    assert Client().get(f"{PRODUCTS_PATH}future/").status_code == 404
    assert Client().get(f"{PRODUCTS_PATH}no-media/").status_code == 404


def test_catalog_filters_sorting_and_unknown_parameters_are_bounded() -> None:
    brand = create_brand()
    category = create_category()
    create_published_product(
        name="Zulu",
        slug="zulu",
        brand=brand,
        category=category,
        material="تیتانیوم",
        shape="گرد",
        color="طلایی",
    )
    create_published_product(
        name="Alpha",
        slug="alpha",
        brand=brand,
        category=category,
        material="استیل",
        shape="مربعی",
        color="مشکی",
    )

    filtered = Client().get(
        PRODUCTS_PATH,
        {"brand": "Ray-Ban", "category": "sun-men", "material": "استیل", "sort": "name-asc"},
    )
    assert filtered.status_code == 200
    assert [item["slug"] for item in filtered.json()["results"]] == ["alpha"]

    ordered = Client().get(PRODUCTS_PATH, {"sort": "name-desc"})
    assert ordered.status_code == 200
    assert [item["slug"] for item in ordered.json()["results"]] == ["zulu", "alpha"]

    assert Client().get(PRODUCTS_PATH, {"sort": "price-desc"}).status_code == 400
    assert Client().get(PRODUCTS_PATH, {"secret_field": "x"}).status_code == 400
    assert Client().get(PRODUCTS_PATH, {"brand": "Unknown"}).status_code == 400


def test_catalog_pagination_is_bounded() -> None:
    brand = create_brand()
    category = create_category()
    for index in range(3):
        create_published_product(
            name=f"Product {index}",
            slug=f"product-{index}",
            brand=brand,
            category=category,
        )

    response = Client().get(PRODUCTS_PATH, {"page_size": 2})
    assert response.status_code == 200
    assert response.json()["count"] == 3
    assert len(response.json()["results"]) == 2

    bounded = Client().get(PRODUCTS_PATH, {"page_size": 1000})
    assert bounded.status_code == 200
    assert len(bounded.json()["results"]) == 3


def test_case_insensitive_sku_and_single_default_variant_are_database_invariants() -> None:
    product = create_published_product()
    ProductVariant.objects.create(product=product, sku="SKU-ONE", is_default=True)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ProductVariant.objects.create(product=product, sku="sku-one")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ProductVariant.objects.create(product=product, sku="SKU-TWO", is_default=True)


def test_published_product_requires_publication_time_in_database() -> None:
    brand = create_brand()
    category = create_category()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Product.objects.create(
                name="Invalid published",
                slug="invalid-published",
                brand=brand,
                category=category,
                status=Product.Status.PUBLISHED,
                published_at=None,
            )


def test_category_cycles_are_rejected_by_model_validation() -> None:
    first = create_category(name="First", slug="first")
    second = Category.objects.create(name="Second", slug="second", parent=first)
    first.parent = second

    with pytest.raises(DjangoValidationError):
        first.full_clean()


def test_cross_product_variant_option_and_media_are_rejected_by_validation() -> None:
    first = create_published_product()
    second_brand = create_brand("Second", "second")
    second_category = create_category("Second", "second")
    second = create_published_product(
        name="Second",
        slug="second",
        brand=second_brand,
        category=second_category,
    )
    option = ProductOption.objects.create(product=first, key="size", label="اندازه")
    value = ProductOptionValue.objects.create(option=option, value="m", label="متوسط")
    second_variant = ProductVariant.objects.create(product=second, sku="SECOND-M")

    selection = ProductVariantOption(variant=second_variant, option=option, value=value)
    with pytest.raises(DjangoValidationError):
        selection.full_clean()

    media = ProductMedia(
        product=first,
        variant=second_variant,
        file=SimpleUploadedFile("cross.jpg", b"x", content_type="image/jpeg"),
        alt="cross",
    )
    with pytest.raises(DjangoValidationError):
        media.full_clean()


def test_prefetched_catalog_list_has_a_bounded_query_count() -> None:
    brand = create_brand()
    category = create_category()
    for index in range(3):
        product = create_published_product(
            name=f"Query {index}",
            slug=f"query-{index}",
            brand=brand,
            category=category,
        )
        option = ProductOption.objects.create(product=product, key="color", label="رنگ")
        value = ProductOptionValue.objects.create(option=option, value="black", label="مشکی")
        variant = ProductVariant.objects.create(product=product, sku=f"QUERY-{index}")
        ProductVariantOption.objects.create(variant=variant, option=option, value=value)

    with CaptureQueriesContext(connection) as queries:
        response = Client().get(PRODUCTS_PATH)

    assert response.status_code == 200
    assert len(queries) <= 12


def test_openapi_contains_catalog_routes() -> None:
    response = Client().get("/api/v1/schema/")
    assert response.status_code == 200
    schema = response.content.decode()
    assert "/api/v1/catalog/brands/" in schema
    assert "/api/v1/catalog/categories/" in schema
    assert "/api/v1/catalog/products/" in schema
    assert "/api/v1/catalog/products/{slug}/" in schema
