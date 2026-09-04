from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from apps.accounts.models import Address, User
from apps.cart.models import Cart
from apps.cart.services import add_cart_line
from apps.catalog.models import (
    Brand,
    Category,
    Product,
    ProductOption,
    ProductOptionValue,
    ProductVariant,
    ProductVariantOption,
)
from apps.checkout.models import CheckoutSession, CheckoutTaxPolicy, ShippingMethod, ShippingZone
from apps.checkout.services import create_checkout, finalize_checkout
from apps.commerce.models import InventoryReservation, VariantInventory, VariantPrice
from apps.orders.models import Order, OrderLine
from apps.orders.selectors import order_for_user
from apps.orders.serializers import order_payload
from apps.orders.services import (
    OrderConflictError,
    OrderStaleError,
    OrderTransitionError,
    advance_fulfillment,
    cancel_order,
    confirm_order_after_verified_payment,
    create_order,
)
from django.db import IntegrityError, close_old_connections, transaction
from django.test import Client
from django.utils import timezone

pytestmark = pytest.mark.django_db(transaction=True)

ORDERS_PATH = "/api/v1/orders/"


def create_user(email: str) -> User:
    return User.objects.create_user(
        username=email,
        email=email,
        password="Correct-Horse-Battery-44",
    )


def create_address(user: User, *, label: str = "Home") -> Address:
    return Address.objects.create(
        user=user,
        label=label,
        recipient_name="Order Customer",
        recipient_phone="+989121234567",
        country_code="IR",
        province="Tehran",
        city="Tehran",
        postal_code="1234567890",
        address_line1="Snapshot street",
        address_line2="",
    )


def configure_checkout_policy() -> ShippingMethod:
    zone = ShippingZone.objects.create(
        code="tehran-city",
        name="Tehran city",
        country_code="IR",
        province="Tehran",
        city="Tehran",
    )
    method = ShippingMethod.objects.create(
        zone=zone,
        code="standard",
        name="Standard delivery",
        flat_rate_toman=Decimal(50_000),
        delivery_min_days=1,
        delivery_max_days=3,
    )
    CheckoutTaxPolicy.objects.create(
        country_code="IR",
        rate_bps=1_000,
        applies_to_shipping=False,
        is_active=True,
    )
    return method


def create_sellable_variant(
    *,
    slug: str,
    stock: int = 5,
    price: int = 200_000,
    with_option: bool = False,
) -> ProductVariant:
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
    if with_option:
        option = ProductOption.objects.create(
            product=product,
            key="color",
            label="Color",
            position=1,
        )
        value = ProductOptionValue.objects.create(
            option=option,
            value="black",
            label="Black",
            position=1,
        )
        ProductVariantOption.objects.create(variant=variant, option=option, value=value)
    VariantPrice.objects.create(variant=variant, amount_toman=Decimal(price))
    VariantInventory.objects.create(variant=variant, on_hand=stock)
    return variant


def prepare_ready_checkout(
    *,
    email: str,
    slug: str,
    quantity: int = 2,
    stock: int = 5,
    price: int = 200_000,
    with_option: bool = False,
) -> tuple[User, Address, ProductVariant, CheckoutSession]:
    user = create_user(email)
    address = create_address(user)
    method = configure_checkout_policy()
    variant = create_sellable_variant(
        slug=slug,
        stock=stock,
        price=price,
        with_option=with_option,
    )
    add_cart_line(user, variant.pk, quantity=quantity)
    checkout = create_checkout(
        user,
        address_id=address.pk,
        shipping_method_code=method.code,
        idempotency_key=uuid4(),
    )
    checkout = finalize_checkout(user, checkout.pk, idempotency_key=uuid4())
    return user, address, variant, checkout


def authenticated_client(user: User) -> Client:
    client = Client()
    client.force_login(user, backend="apps.accounts.backends.EmailAuthenticationBackend")
    return client


def test_order_creation_snapshots_checkout_and_keeps_inventory_reserved_until_payment() -> None:
    user, address, variant, checkout = prepare_ready_checkout(
        email="order-snapshot@example.com",
        slug="order-snapshot",
        with_option=True,
    )
    inventory = VariantInventory.objects.get(variant=variant)
    original_on_hand = inventory.on_hand

    result = create_order(
        user,
        checkout_id=checkout.pk,
        idempotency_key=uuid4(),
    )
    order = result.order
    checkout.refresh_from_db()
    cart = Cart.objects.get(pk=checkout.cart_id)
    reservation = InventoryReservation.objects.get(order_line__order=order)
    line = OrderLine.objects.get(order=order)
    inventory.refresh_from_db()

    assert result.created is True
    assert order.status == Order.Status.PENDING_PAYMENT
    assert checkout.status == CheckoutSession.Status.COMPLETED
    assert cart.status == Cart.Status.CONVERTED
    assert reservation.status == InventoryReservation.Status.ACTIVE
    assert inventory.on_hand == original_on_hand
    assert order.address_snapshot["addressLine1"] == "Snapshot street"
    assert line.source_product_name == variant.product.name
    assert line.source_variant_sku == variant.sku
    assert line.option_snapshot == {
        "color": {"value": "black", "label": "Black", "optionLabel": "Color"}
    }

    before = order_payload(order_for_user(user, order.public_id), include_lines=True)
    Address.objects.filter(pk=address.pk).update(address_line1="Changed later")
    Product.objects.filter(pk=variant.product_id).update(name="Changed product")
    ProductVariant.objects.filter(pk=variant.pk).update(sku="CHANGED-SKU")
    VariantPrice.objects.filter(variant=variant).update(amount_toman=Decimal(999_999))
    ProductOptionValue.objects.filter(option__product_id=variant.product_id).update(
        value="white",
        label="White",
    )
    after = order_payload(order_for_user(user, order.public_id), include_lines=True)

    assert after == before


def test_order_create_is_idempotent_and_key_reuse_for_another_checkout_conflicts() -> None:
    user, address, _variant, checkout = prepare_ready_checkout(
        email="order-idempotency@example.com",
        slug="order-idempotency-a",
    )
    key = uuid4()
    first = create_order(user, checkout_id=checkout.pk, idempotency_key=key)
    replay = create_order(user, checkout_id=checkout.pk, idempotency_key=key)
    replay_other_key = create_order(user, checkout_id=checkout.pk, idempotency_key=uuid4())

    assert first.created is True
    assert replay.created is False
    assert replay_other_key.created is False
    assert replay.order.pk == first.order.pk == replay_other_key.order.pk
    assert Order.objects.count() == 1
    assert OrderLine.objects.count() == 1

    second_variant = create_sellable_variant(slug="order-idempotency-b")
    add_cart_line(user, second_variant.pk, quantity=1)
    second_checkout = create_checkout(
        user,
        address_id=address.pk,
        shipping_method_code="standard",
        idempotency_key=uuid4(),
    )
    second_checkout = finalize_checkout(user, second_checkout.pk, idempotency_key=uuid4())

    with pytest.raises(OrderConflictError):
        create_order(user, checkout_id=second_checkout.pk, idempotency_key=key)


def test_order_database_enforces_money_and_line_total_invariants() -> None:
    user, _address, _variant, checkout = prepare_ready_checkout(
        email="order-db@example.com",
        slug="order-db",
    )
    order = create_order(user, checkout_id=checkout.pk, idempotency_key=uuid4()).order
    line = OrderLine.objects.get(order=order)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Order.objects.filter(pk=order.pk).update(payable_toman=int(order.payable_toman) + 1)

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            OrderLine.objects.filter(pk=line.pk).update(
                line_total_toman=int(line.line_total_toman) + 1
            )


def test_create_order_revalidates_ready_checkout_and_rejects_price_drift() -> None:
    user, _address, variant, checkout = prepare_ready_checkout(
        email="order-stale@example.com",
        slug="order-stale",
    )
    VariantPrice.objects.filter(variant=variant).update(amount_toman=Decimal(210_000))

    with pytest.raises(OrderStaleError):
        create_order(user, checkout_id=checkout.pk, idempotency_key=uuid4())
    assert Order.objects.count() == 0


def test_cancel_releases_reservation_and_confirm_cannot_run_after_cancel() -> None:
    user, _address, variant, checkout = prepare_ready_checkout(
        email="order-cancel@example.com",
        slug="order-cancel",
        stock=5,
        quantity=2,
    )
    order = create_order(user, checkout_id=checkout.pk, idempotency_key=uuid4()).order
    inventory = VariantInventory.objects.get(variant=variant)
    before = inventory.on_hand

    cancelled = cancel_order(user, order.public_id)
    replay = cancel_order(user, order.public_id)
    reservation = InventoryReservation.objects.get(order_line__order=order)
    inventory.refresh_from_db()

    assert cancelled.status == Order.Status.CANCELLED
    assert replay.status == Order.Status.CANCELLED
    assert reservation.status == InventoryReservation.Status.RELEASED
    assert inventory.on_hand == before
    with pytest.raises(OrderTransitionError):
        confirm_order_after_verified_payment(order.pk)


def test_verified_payment_confirmation_consumes_once_and_fulfillment_is_forward_only() -> None:
    user, _address, variant, checkout = prepare_ready_checkout(
        email="order-confirm@example.com",
        slug="order-confirm",
        stock=5,
        quantity=2,
    )
    order = create_order(user, checkout_id=checkout.pk, idempotency_key=uuid4()).order
    inventory = VariantInventory.objects.get(variant=variant)
    before = inventory.on_hand

    confirmed = confirm_order_after_verified_payment(order.pk)
    replay = confirm_order_after_verified_payment(order.pk)
    inventory.refresh_from_db()
    reservation = InventoryReservation.objects.get(order_line__order=order)

    assert confirmed.status == Order.Status.CONFIRMED
    assert replay.status == Order.Status.CONFIRMED
    assert reservation.status == InventoryReservation.Status.CONSUMED
    assert inventory.on_hand == before - 2

    processing = advance_fulfillment(order.pk, target_status=Order.Status.PROCESSING)
    shipped = advance_fulfillment(order.pk, target_status=Order.Status.SHIPPED)
    delivered = advance_fulfillment(order.pk, target_status=Order.Status.DELIVERED)
    assert (processing.status, shipped.status, delivered.status) == (
        Order.Status.PROCESSING,
        Order.Status.SHIPPED,
        Order.Status.DELIVERED,
    )
    with pytest.raises(OrderTransitionError):
        advance_fulfillment(order.pk, target_status=Order.Status.PROCESSING)


def test_order_api_is_authenticated_user_scoped_and_has_no_payment_confirm_route() -> None:
    owner, _address, _variant, checkout = prepare_ready_checkout(
        email="order-api-owner@example.com",
        slug="order-api-owner",
    )
    order = create_order(owner, checkout_id=checkout.pk, idempotency_key=uuid4()).order
    other = create_user("order-api-other@example.com")

    anonymous = Client()
    assert anonymous.get(ORDERS_PATH).status_code in {401, 403}

    owner_client = authenticated_client(owner)
    list_response = owner_client.get(ORDERS_PATH)
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()["orders"]] == [str(order.public_id)]

    detail_path = f"/api/v1/orders/{order.public_id}/"
    cancel_path = f"/api/v1/orders/{order.public_id}/cancel/"
    assert owner_client.get(detail_path).status_code == 200

    other_client = authenticated_client(other)
    assert other_client.get(detail_path).status_code == 404
    assert other_client.post(cancel_path, content_type="application/json").status_code == 404
    assert (
        owner_client.post(f"{detail_path}confirm/", content_type="application/json").status_code
        == 404
    )


def test_order_create_api_accepts_only_checkout_identity_and_server_snapshots() -> None:
    user, _address, _variant, checkout = prepare_ready_checkout(
        email="order-api-create@example.com",
        slug="order-api-create",
    )
    client = authenticated_client(user)
    response = client.post(
        ORDERS_PATH,
        {
            "checkoutId": str(checkout.pk),
            "idempotencyKey": str(uuid4()),
            "status": "confirmed",
            "payableToman": 1,
            "currency": "USD",
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    body = response.json()["order"]
    assert body["status"] == Order.Status.PENDING_PAYMENT
    assert body["totals"]["payable"]["amount"] == 490_000
    assert body["totals"]["payable"]["currency"] == "IRR"
    assert body["totals"]["payable"]["displayUnit"] == "تومان"


def test_concurrent_create_for_one_checkout_produces_exactly_one_order() -> None:
    user, _address, _variant, checkout = prepare_ready_checkout(
        email="order-race-create@example.com",
        slug="order-race-create",
    )

    def attempt(user_id: int, checkout_id: UUID, key: UUID) -> UUID:
        close_old_connections()
        try:
            thread_user = User.objects.get(pk=user_id)
            result = create_order(
                thread_user,
                checkout_id=checkout_id,
                idempotency_key=key,
            )
            return UUID(str(result.order.pk))
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda key: attempt(user.pk, checkout.pk, key),
                [uuid4(), uuid4()],
            )
        )

    assert len(set(results)) == 1
    assert Order.objects.count() == 1
    assert OrderLine.objects.count() == 1
    reservation = InventoryReservation.objects.get(order_line__order_id=results[0])
    assert reservation.status == InventoryReservation.Status.ACTIVE


def test_confirmation_and_cancellation_race_serializes_to_one_valid_outcome() -> None:
    user, _address, variant, checkout = prepare_ready_checkout(
        email="order-race-transition@example.com",
        slug="order-race-transition",
        stock=5,
        quantity=2,
    )
    order = create_order(user, checkout_id=checkout.pk, idempotency_key=uuid4()).order

    def confirm(order_id: UUID) -> str:
        close_old_connections()
        try:
            confirm_order_after_verified_payment(order_id)
            return "confirmed"
        except OrderTransitionError:
            return "conflict"
        finally:
            close_old_connections()

    def cancel(user_id: int, public_id: UUID) -> str:
        close_old_connections()
        try:
            thread_user = User.objects.get(pk=user_id)
            cancel_order(thread_user, public_id)
            return "cancelled"
        except OrderTransitionError:
            return "conflict"
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as executor:
        confirm_future = executor.submit(confirm, order.pk)
        cancel_future = executor.submit(cancel, user.pk, order.public_id)
        outcomes = [confirm_future.result(), cancel_future.result()]

    order.refresh_from_db()
    reservation = InventoryReservation.objects.get(order_line__order=order)
    inventory = VariantInventory.objects.get(variant=variant)

    assert outcomes.count("conflict") == 1
    assert order.status in {Order.Status.CONFIRMED, Order.Status.CANCELLED}
    if order.status == Order.Status.CONFIRMED:
        assert reservation.status == InventoryReservation.Status.CONSUMED
        assert inventory.on_hand == 3
    else:
        assert reservation.status == InventoryReservation.Status.RELEASED
        assert inventory.on_hand == 5
