from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

import pytest
from apps.catalog.models import Brand, Category, Product, ProductMedia, ProductVariant
from apps.commerce.models import InventoryReservation, VariantInventory, VariantPrice
from apps.commerce.services import (
    InventoryUnavailableError,
    ReservationStateError,
    available_quantity,
    consume_reservation,
    release_reservation,
    reserve_variant,
    set_on_hand,
)
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, close_old_connections, transaction
from django.test import Client
from django.utils import timezone

pytestmark = pytest.mark.django_db

PRODUCTS_PATH = "/api/v1/catalog/products/"


def create_sellable_variant(*, slug: str = "commerce-product") -> ProductVariant:
    brand = Brand.objects.create(name=f"Brand {slug}", slug=f"brand-{slug}")
    category = Category.objects.create(name=f"Category {slug}", slug=f"category-{slug}")
    product = Product.objects.create(
        name=f"Product {slug}",
        slug=slug,
        brand=brand,
        category=category,
        status=Product.Status.PUBLISHED,
        published_at=timezone.now(),
        material="acetate",
        shape="round",
        color="black",
    )
    ProductMedia.objects.create(
        product=product,
        file=SimpleUploadedFile("front.jpg", b"b03-media", content_type="image/jpeg"),
        alt="Product front",
        position=0,
    )
    return ProductVariant.objects.create(
        product=product,
        sku=f"SKU-{slug}",
        is_default=True,
        is_active=True,
    )


def test_authoritative_catalog_price_and_availability_project_from_default_variant() -> None:
    variant = create_sellable_variant()
    VariantPrice.objects.create(
        variant=variant,
        amount_toman=Decimal("1250000"),
        compare_at_toman=Decimal("1500000"),
    )
    inventory = VariantInventory.objects.create(variant=variant, on_hand=5)
    InventoryReservation.objects.create(
        inventory=inventory,
        quantity=2,
        expires_at=timezone.now() + timedelta(minutes=10),
    )

    response = Client().get(PRODUCTS_PATH)

    assert response.status_code == 200
    item = response.json()["results"][0]
    assert item["priceContract"]["authoritative"] is True
    assert item["priceContract"]["current"] == {
        "amount": 1_250_000,
        "currency": "IRR",
        "displayUnit": "تومان",
    }
    assert item["priceContract"]["compareAt"] == {
        "amount": 1_500_000,
        "currency": "IRR",
        "displayUnit": "تومان",
    }
    assert item["price"] == 1_250_000
    assert item["originalPrice"] == 1_500_000
    assert item["availability"]["authoritative"] is True
    assert item["availability"]["status"] == "in-stock"
    assert item["availability"]["maxQuantity"] == 3
    assert item["inStock"] is True
    assert item["variants"][0]["price"]["authoritative"] is True
    assert item["variants"][0]["availability"]["maxQuantity"] == 3
    assert any(badge["kind"] == "sale" for badge in item["badges"])


def test_missing_price_or_inventory_remains_fail_closed() -> None:
    variant = create_sellable_variant(slug="fail-closed")
    VariantPrice.objects.create(variant=variant, amount_toman=Decimal("200000"), is_active=False)
    VariantInventory.objects.create(variant=variant, on_hand=4, is_active=False)

    item = Client().get(PRODUCTS_PATH).json()["results"][0]

    assert item["priceContract"]["authoritative"] is False
    assert item["price"] == 0
    assert item["originalPrice"] is None
    assert item["availability"]["authoritative"] is False
    assert item["availability"]["status"] == "unknown"
    assert item["inStock"] is False


def test_price_constraints_reject_negative_and_invalid_compare_at() -> None:
    first = create_sellable_variant(slug="negative-price")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            VariantPrice.objects.create(variant=first, amount_toman=Decimal("-1"))

    second = create_sellable_variant(slug="bad-compare")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            VariantPrice.objects.create(
                variant=second,
                amount_toman=Decimal("1000"),
                compare_at_toman=Decimal("1000"),
            )


def test_expired_hold_is_not_counted_and_is_lazily_normalized_on_reserve() -> None:
    variant = create_sellable_variant(slug="expired")
    inventory = VariantInventory.objects.create(variant=variant, on_hand=3)
    expired = InventoryReservation.objects.create(
        inventory=inventory,
        quantity=3,
        expires_at=timezone.now() - timedelta(seconds=1),
    )

    assert available_quantity(inventory) == 3
    current = reserve_variant(variant.id, quantity=3)

    expired.refresh_from_db()
    assert expired.status == InventoryReservation.Status.EXPIRED
    assert current.status == InventoryReservation.Status.ACTIVE
    inventory.refresh_from_db()
    assert available_quantity(inventory) == 0


def test_release_is_idempotent_and_does_not_free_twice() -> None:
    variant = create_sellable_variant(slug="release")
    inventory = VariantInventory.objects.create(variant=variant, on_hand=2)
    reservation = reserve_variant(variant.id, quantity=2)

    first = release_reservation(reservation.id)
    second = release_reservation(reservation.id)

    assert first.status == InventoryReservation.Status.RELEASED
    assert second.status == InventoryReservation.Status.RELEASED
    inventory.refresh_from_db()
    assert inventory.on_hand == 2
    assert available_quantity(inventory) == 2


def test_consume_decrements_on_hand_once_and_rejects_second_consume() -> None:
    variant = create_sellable_variant(slug="consume")
    inventory = VariantInventory.objects.create(variant=variant, on_hand=4)
    reservation = reserve_variant(variant.id, quantity=3)

    consumed = consume_reservation(reservation.id)

    assert consumed.status == InventoryReservation.Status.CONSUMED
    inventory.refresh_from_db()
    assert inventory.on_hand == 1
    assert available_quantity(inventory) == 1

    with pytest.raises(ReservationStateError):
        consume_reservation(reservation.id)
    inventory.refresh_from_db()
    assert inventory.on_hand == 1


def test_on_hand_cannot_be_reduced_below_active_holds() -> None:
    variant = create_sellable_variant(slug="adjust")
    inventory = VariantInventory.objects.create(variant=variant, on_hand=5)
    reserve_variant(variant.id, quantity=4)

    with pytest.raises(InventoryUnavailableError):
        set_on_hand(variant.id, quantity=3)

    inventory.refresh_from_db()
    assert inventory.on_hand == 5


@pytest.mark.django_db(transaction=True)
def test_concurrent_reservations_cannot_oversell_same_variant() -> None:
    variant = create_sellable_variant(slug="concurrent")
    VariantInventory.objects.create(variant=variant, on_hand=5)

    def attempt_reservation() -> bool:
        close_old_connections()
        try:
            reserve_variant(variant.id, quantity=4)
        except InventoryUnavailableError:
            return False
        finally:
            close_old_connections()
        return True

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _index: attempt_reservation(), range(2)))

    assert sorted(results) == [False, True]
    inventory = VariantInventory.objects.get(variant=variant)
    assert available_quantity(inventory) == 1
    assert InventoryReservation.objects.filter(
        inventory=inventory,
        status=InventoryReservation.Status.ACTIVE,
    ).count() == 1
