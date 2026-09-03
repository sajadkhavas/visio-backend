from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

import pytest
from apps.accounts.models import User
from apps.cart.models import Cart, CartLine, WishlistItem
from apps.cart.services import BrowserCartLine, add_cart_line, get_or_create_active_cart, merge_browser_cart
from apps.catalog.models import Brand, Category, Product, ProductVariant
from apps.commerce.models import InventoryReservation, VariantInventory, VariantPrice
from django.db import IntegrityError, close_old_connections, transaction
from django.test import Client
from django.utils import timezone

pytestmark = pytest.mark.django_db

CART_PATH = "/api/v1/cart/"
CART_LINES_PATH = "/api/v1/cart/lines/"
CART_VALIDATE_PATH = "/api/v1/cart/validate/"
CART_IMPORT_PATH = "/api/v1/cart/import/"
WISHLIST_PATH = "/api/v1/wishlist/"


def create_user(email: str) -> User:
    return User.objects.create_user(
        username=email,
        email=email,
        password="Correct-Horse-Battery-44",
    )


def create_sellable_variant(*, slug: str, stock: int = 5, price: int = 100_000) -> ProductVariant:
    brand = Brand.objects.create(name=f"Brand {slug}", slug=f"brand-{slug}")
    category = Category.objects.create(name=f"Category {slug}", slug=f"category-{slug}")
    product = Product.objects.create(
        name=f"Product {slug}",
        slug=slug,
        brand=brand,
        category=category,
        status=Product.Status.PUBLISHED,
        published_at=timezone.now(),
    )
    variant = ProductVariant.objects.create(
        product=product,
        sku=f"SKU-{slug}",
        is_default=True,
        is_active=True,
    )
    VariantPrice.objects.create(variant=variant, amount_toman=Decimal(price))
    VariantInventory.objects.create(variant=variant, on_hand=stock)
    return variant


def authenticated_client(user: User) -> Client:
    client = Client()
    client.force_login(user, backend="apps.accounts.backends.EmailAuthenticationBackend")
    return client


def test_one_active_cart_per_user_is_database_enforced() -> None:
    user = create_user("cart-unique@example.com")
    Cart.objects.create(user=user)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Cart.objects.create(user=user)


def test_unique_variant_per_cart_and_quantity_bounds_are_database_enforced() -> None:
    user = create_user("line-constraints@example.com")
    variant = create_sellable_variant(slug="line-constraints")
    cart = Cart.objects.create(user=user)
    CartLine.objects.create(cart=cart, variant=variant, quantity=1)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CartLine.objects.create(cart=cart, variant=variant, quantity=1)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CartLine.objects.filter(cart=cart, variant=variant).update(quantity=100)


def test_add_cart_line_does_not_reserve_inventory() -> None:
    user = create_user("no-reservation@example.com")
    variant = create_sellable_variant(slug="no-reservation", stock=2)

    add_cart_line(user, variant.id, quantity=2)

    line = CartLine.objects.get(cart__user=user, variant=variant)
    assert line.quantity == 2
    assert InventoryReservation.objects.count() == 0


def test_cart_api_projects_b03_price_availability_and_frontend_identity() -> None:
    user = create_user("projection@example.com")
    variant = create_sellable_variant(slug="projection", stock=4, price=321_000)
    client = authenticated_client(user)

    response = client.post(
        CART_LINES_PATH,
        {"variantId": str(variant.id), "quantity": 2},
        content_type="application/json",
    )

    assert response.status_code == 200
    payload = response.json()
    cart = payload["cart"]
    assert cart["version"] == 2
    assert cart["serverRevision"] >= 2
    assert cart["totals"]["provisional"] is True
    assert cart["totals"]["subtotal"]["amount"] == 642_000
    assert cart["totals"]["payable"] is None
    item = cart["items"][0]
    assert item["identity"]["productId"] == str(variant.product_id)
    assert item["identity"]["variantId"] == str(variant.id)
    assert item["identity"]["key"] == f"{variant.product_id}::{variant.id}::default"
    assert item["availability"]["status"] == "available"
    assert item["priceSnapshot"]["amount"] == 321_000
    assert item["priceSnapshot"]["currency"] == "IRR"
    assert item["priceSnapshot"]["displayUnit"] == "تومان"
    assert item["priceSnapshot"]["authority"] == "server-validated"


def test_cart_api_add_set_remove_and_clear_are_user_scoped() -> None:
    owner = create_user("owner@example.com")
    other = create_user("other@example.com")
    variant = create_sellable_variant(slug="mutations")
    owner_client = authenticated_client(owner)
    other_client = authenticated_client(other)

    add_response = owner_client.post(
        CART_LINES_PATH,
        {"variantId": str(variant.id), "quantity": 2},
        content_type="application/json",
    )
    assert add_response.status_code == 200

    detail = f"{CART_LINES_PATH}{variant.id}/"
    patch_response = owner_client.patch(
        detail,
        {"quantity": 4},
        content_type="application/json",
    )
    assert patch_response.status_code == 200
    assert CartLine.objects.get(cart__user=owner, variant=variant).quantity == 4

    other_response = other_client.patch(
        detail,
        {"quantity": 1},
        content_type="application/json",
    )
    assert other_response.status_code == 404
    assert CartLine.objects.get(cart__user=owner, variant=variant).quantity == 4

    assert owner_client.delete(detail).status_code == 200
    assert not CartLine.objects.filter(cart__user=owner, variant=variant).exists()

    owner_client.post(
        CART_LINES_PATH,
        {"variantId": str(variant.id), "quantity": 1},
        content_type="application/json",
    )
    assert owner_client.delete(CART_PATH).status_code == 200
    assert not CartLine.objects.filter(cart__user=owner).exists()


def test_validate_clamps_to_positive_authoritative_stock_without_reserving() -> None:
    user = create_user("validate@example.com")
    variant = create_sellable_variant(slug="validate", stock=2)
    client = authenticated_client(user)
    client.post(
        CART_LINES_PATH,
        {"variantId": str(variant.id), "quantity": 5},
        content_type="application/json",
    )

    response = client.post(CART_VALIDATE_PATH, {"items": []}, content_type="application/json")

    assert response.status_code == 200
    body = response.json()
    assert CartLine.objects.get(cart__user=user, variant=variant).quantity == 2
    expected_issue = {
        "type": "quantity-adjusted",
        "key": body["cart"]["items"][0]["identity"]["key"],
        "allowed": 2,
    }
    assert expected_issue in body["issues"]
    assert InventoryReservation.objects.count() == 0


def test_validate_reports_sold_out_without_zeroing_persisted_quantity() -> None:
    user = create_user("soldout@example.com")
    variant = create_sellable_variant(slug="soldout", stock=0)
    client = authenticated_client(user)
    client.post(
        CART_LINES_PATH,
        {"variantId": str(variant.id), "quantity": 1},
        content_type="application/json",
    )

    response = client.post(CART_VALIDATE_PATH, {"items": []}, content_type="application/json")

    assert response.status_code == 200
    body = response.json()
    assert body["cart"]["items"][0]["availability"]["status"] == "sold-out"
    assert any(issue["type"] == "sold-out" for issue in body["issues"])
    assert CartLine.objects.get(cart__user=user, variant=variant).quantity == 1


def test_validate_reports_client_price_mismatch_without_accepting_client_price() -> None:
    user = create_user("price-mismatch@example.com")
    variant = create_sellable_variant(slug="price-mismatch", stock=5, price=500_000)
    client = authenticated_client(user)
    client.post(
        CART_LINES_PATH,
        {"variantId": str(variant.id), "quantity": 1},
        content_type="application/json",
    )

    response = client.post(
        CART_VALIDATE_PATH,
        {
            "items": [
                {
                    "identity": {"variantId": str(variant.id)},
                    "quantity": 1,
                    "priceSnapshot": {
                        "amount": 1,
                        "currency": "IRR",
                        "displayUnit": "تومان",
                        "authority": "client-snapshot",
                        "capturedAt": None,
                        "revision": None,
                    },
                }
            ]
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    body = response.json()
    item = body["cart"]["items"][0]
    assert item["priceSnapshot"]["amount"] == 500_000
    assert item["priceMismatch"]["status"] == "changed"
    assert item["priceMismatch"]["previous"]["amount"] == 1
    assert item["priceMismatch"]["current"]["amount"] == 500_000
    assert any(issue["type"] == "price-changed" for issue in body["issues"])


def test_browser_import_deduplicates_and_is_result_state_idempotent() -> None:
    user = create_user("import@example.com")
    variant = create_sellable_variant(slug="import")
    add_cart_line(user, variant.id, quantity=2)

    payload = [
        BrowserCartLine(variant_id=variant.id, quantity=1),
        BrowserCartLine(variant_id=variant.id, quantity=2),
    ]
    first, first_issues = merge_browser_cart(user, payload)
    second, second_issues = merge_browser_cart(user, payload)

    assert first_issues == []
    assert second_issues == []
    assert first.id == second.id
    assert CartLine.objects.get(cart__user=user, variant=variant).quantity == 3
    assert CartLine.objects.filter(cart__user=user, variant=variant).count() == 1


def test_browser_import_skips_unavailable_variant_deterministically() -> None:
    user = create_user("import-stale@example.com")
    variant = create_sellable_variant(slug="import-stale")
    variant.is_active = False
    variant.save(update_fields=("is_active", "updated_at"))
    client = authenticated_client(user)

    response = client.post(
        CART_IMPORT_PATH,
        {
            "items": [
                {
                    "identity": {"variantId": str(variant.id)},
                    "quantity": 1,
                    "priceSnapshot": None,
                }
            ]
        },
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["importIssues"] == [
        {"variantId": str(variant.id), "code": "variant-unavailable"}
    ]
    assert not CartLine.objects.filter(cart__user=user).exists()


def test_wishlist_add_remove_are_idempotent_and_user_isolated() -> None:
    first = create_user("wishlist-first@example.com")
    second = create_user("wishlist-second@example.com")
    variant = create_sellable_variant(slug="wishlist")
    product_id = variant.product_id
    first_client = authenticated_client(first)
    second_client = authenticated_client(second)
    item_path = f"{WISHLIST_PATH}{product_id}/"

    assert first_client.put(item_path).status_code == 200
    assert first_client.put(item_path).status_code == 200
    assert WishlistItem.objects.filter(user=first, product_id=product_id).count() == 1
    assert second_client.get(WISHLIST_PATH).json() == {"productIds": []}

    assert first_client.delete(item_path).status_code == 204
    assert first_client.delete(item_path).status_code == 204
    assert not WishlistItem.objects.filter(user=first, product_id=product_id).exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_adds_leave_one_line_with_deterministic_quantity() -> None:
    user = create_user("concurrent-cart@example.com")
    variant = create_sellable_variant(slug="concurrent-cart")
    get_or_create_active_cart(user)

    def add_once() -> None:
        close_old_connections()
        try:
            worker_user = User.objects.get(pk=user.pk)
            add_cart_line(worker_user, variant.id, quantity=1)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        list(executor.map(lambda _index: add_once(), range(2)))

    assert CartLine.objects.filter(cart__user=user, variant=variant).count() == 1
    assert CartLine.objects.get(cart__user=user, variant=variant).quantity == 2


def test_existing_inventory_reservation_only_affects_projection_not_cart_mutation() -> None:
    user = create_user("reserved-projection@example.com")
    variant = create_sellable_variant(slug="reserved-projection", stock=5)
    inventory = VariantInventory.objects.get(variant=variant)
    InventoryReservation.objects.create(
        inventory=inventory,
        quantity=4,
        expires_at=timezone.now() + timedelta(minutes=10),
    )
    client = authenticated_client(user)

    response = client.post(
        CART_LINES_PATH,
        {"variantId": str(variant.id), "quantity": 3},
        content_type="application/json",
    )

    assert response.status_code == 200
    assert response.json()["cart"]["items"][0]["availability"]["status"] == "available"
    assert CartLine.objects.get(cart__user=user, variant=variant).quantity == 3
    assert InventoryReservation.objects.filter(inventory=inventory).count() == 1
