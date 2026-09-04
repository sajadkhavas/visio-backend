from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from apps.accounts.models import Address, User
from apps.cart.services import add_cart_line
from apps.catalog.models import Brand, Category, Product, ProductVariant
from apps.checkout.models import (
    CheckoutLine,
    CheckoutSession,
    CheckoutTaxPolicy,
    ShippingMethod,
    ShippingZone,
)
from apps.checkout.services import (
    CheckoutConflictError,
    CheckoutNotFoundError,
    CheckoutStaleError,
    CheckoutUnavailableError,
    TaxPolicyUnavailableError,
    cancel_checkout,
    create_checkout,
    finalize_checkout,
    get_current_checkout,
    shipping_quotes,
)
from apps.commerce.models import InventoryReservation, VariantInventory, VariantPrice
from django.db import IntegrityError, close_old_connections, transaction
from django.test import Client
from django.utils import timezone

pytestmark = pytest.mark.django_db(transaction=True)

SHIPPING_OPTIONS_PATH = "/api/v1/checkout/shipping-options/"
CHECKOUT_CREATE_PATH = "/api/v1/checkout/sessions/"


def create_user(email: str) -> User:
    return User.objects.create_user(
        username=email,
        email=email,
        password="Correct-Horse-Battery-44",
    )


def create_address(
    user: User,
    *,
    label: str = "Home",
    province: str = "Tehran",
    city: str = "Tehran",
) -> Address:
    return Address.objects.create(
        user=user,
        label=label,
        recipient_name="Checkout Customer",
        recipient_phone="+989121234567",
        country_code="IR",
        province=province,
        city=city,
        postal_code="1234567890",
        address_line1="Example street",
        address_line2="",
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


def configure_checkout_policy(
    *,
    flat_rate: int = 50_000,
    free_over: int | None = None,
    tax_rate_bps: int = 1_000,
    applies_to_shipping: bool = False,
) -> tuple[ShippingZone, ShippingMethod, CheckoutTaxPolicy]:
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
        flat_rate_toman=Decimal(flat_rate),
        free_over_toman=Decimal(free_over) if free_over is not None else None,
        delivery_min_days=1,
        delivery_max_days=3,
    )
    policy = CheckoutTaxPolicy.objects.create(
        country_code="IR",
        rate_bps=tax_rate_bps,
        applies_to_shipping=applies_to_shipping,
        is_active=True,
    )
    return zone, method, policy


def authenticated_client(user: User) -> Client:
    client = Client()
    client.force_login(user, backend="apps.accounts.backends.EmailAuthenticationBackend")
    return client


def prepare_checkout(
    *,
    email: str,
    slug: str,
    quantity: int = 2,
    stock: int = 5,
    price: int = 200_000,
    flat_rate: int = 50_000,
    tax_rate_bps: int = 1_000,
) -> tuple[User, Address, ProductVariant, ShippingMethod, CheckoutSession]:
    user = create_user(email)
    address = create_address(user)
    variant = create_sellable_variant(slug=slug, stock=stock, price=price)
    _zone, method, _policy = configure_checkout_policy(
        flat_rate=flat_rate,
        tax_rate_bps=tax_rate_bps,
    )
    add_cart_line(user, variant.id, quantity=quantity)
    session = create_checkout(
        user,
        address_id=address.pk,
        shipping_method_code=method.code,
        idempotency_key=uuid4(),
    )
    return user, address, variant, method, session


def test_shipping_quotes_require_explicit_tax_policy_and_compute_server_totals() -> None:
    user = create_user("quote@example.com")
    address = create_address(user)
    variant = create_sellable_variant(slug="quote", stock=5, price=200_000)
    zone = ShippingZone.objects.create(
        code="tehran-city",
        name="Tehran city",
        country_code="IR",
        province="Tehran",
        city="Tehran",
    )
    ShippingMethod.objects.create(
        zone=zone,
        code="standard",
        name="Standard delivery",
        flat_rate_toman=Decimal(50_000),
        delivery_min_days=1,
        delivery_max_days=3,
    )
    add_cart_line(user, variant.id, quantity=2)

    with pytest.raises(TaxPolicyUnavailableError):
        shipping_quotes(user, address.pk)

    CheckoutTaxPolicy.objects.create(
        country_code="IR",
        rate_bps=1_000,
        applies_to_shipping=False,
        is_active=True,
    )
    quote = shipping_quotes(user, address.pk)[0]

    assert quote.subtotal_toman == 400_000
    assert quote.discount_toman == 0
    assert quote.shipping_toman == 50_000
    assert quote.tax_toman == 40_000
    assert quote.payable_toman == 490_000
    assert InventoryReservation.objects.count() == 0


def test_checkout_api_ignores_client_money_claims_and_returns_server_truth() -> None:
    user = create_user("api-truth@example.com")
    address = create_address(user)
    variant = create_sellable_variant(slug="api-truth", stock=5, price=200_000)
    _zone, method, _policy = configure_checkout_policy(flat_rate=50_000, tax_rate_bps=1_000)
    add_cart_line(user, variant.id, quantity=2)
    client = authenticated_client(user)

    response = client.post(
        CHECKOUT_CREATE_PATH,
        {
            "addressId": address.pk,
            "shippingMethodCode": method.code,
            "idempotencyKey": str(uuid4()),
            "subtotalToman": 1,
            "shippingToman": 1,
            "taxToman": 1,
            "payableToman": 1,
        },
        content_type="application/json",
    )

    assert response.status_code == 201
    totals = response.json()["checkout"]["totals"]
    assert totals["subtotal"]["amount"] == 400_000
    assert totals["shipping"]["amount"] == 50_000
    assert totals["tax"]["amount"] == 40_000
    assert totals["payable"]["amount"] == 490_000
    assert totals["payable"]["currency"] == "IRR"
    assert totals["payable"]["displayUnit"] == "تومان"


def test_checkout_create_is_idempotent_and_rejects_key_reuse_with_different_inputs() -> None:
    user = create_user("create-idempotency@example.com")
    address = create_address(user)
    variant = create_sellable_variant(slug="create-idempotency")
    zone, method, _policy = configure_checkout_policy()
    ShippingMethod.objects.create(
        zone=zone,
        code="express",
        name="Express delivery",
        flat_rate_toman=Decimal(80_000),
        delivery_min_days=1,
        delivery_max_days=1,
    )
    add_cart_line(user, variant.id, quantity=1)
    key = uuid4()

    first = create_checkout(
        user,
        address_id=address.pk,
        shipping_method_code=method.code,
        idempotency_key=key,
    )
    second = create_checkout(
        user,
        address_id=address.pk,
        shipping_method_code=method.code.upper(),
        idempotency_key=key,
    )

    assert second.pk == first.pk
    assert (
        InventoryReservation.objects.filter(status=InventoryReservation.Status.ACTIVE).count() == 1
    )

    with pytest.raises(CheckoutConflictError):
        create_checkout(
            user,
            address_id=address.pk,
            shipping_method_code="express",
            idempotency_key=key,
        )


def test_checkout_database_enforces_nonterminal_money_and_line_total_invariants() -> None:
    user, _address, _variant, _method, session = prepare_checkout(
        email="db-invariants@example.com",
        slug="db-invariants",
    )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CheckoutSession.objects.create(
                user=user,
                cart=session.cart,
                address=session.address,
                shipping_method=session.shipping_method,
                idempotency_key=uuid4(),
                status=CheckoutSession.Status.ACTIVE,
                cart_revision=session.cart_revision,
                subtotal_toman=session.subtotal_toman,
                discount_toman=session.discount_toman,
                shipping_toman=session.shipping_toman,
                tax_toman=session.tax_toman,
                payable_toman=session.payable_toman,
                tax_rate_bps=session.tax_rate_bps,
                address_snapshot=session.address_snapshot,
                shipping_snapshot=session.shipping_snapshot,
                expires_at=session.expires_at,
            )

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CheckoutSession.objects.filter(pk=session.pk).update(
                payable_toman=int(session.payable_toman) + 1
            )

    line = CheckoutLine.objects.get(checkout=session)
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            CheckoutLine.objects.filter(pk=line.pk).update(
                line_total_toman=int(line.line_total_toman) + 1
            )


def test_cross_user_address_and_checkout_access_are_isolated() -> None:
    owner, _address, _variant, _method, session = prepare_checkout(
        email="checkout-owner@example.com",
        slug="checkout-owner",
    )
    other = create_user("checkout-other@example.com")
    other_address = create_address(other, label="Other")

    with pytest.raises(CheckoutNotFoundError):
        create_checkout(
            owner,
            address_id=other_address.pk,
            shipping_method_code="standard",
            idempotency_key=uuid4(),
        )

    other_client = authenticated_client(other)
    finalize_path = f"/api/v1/checkout/sessions/{session.pk}/finalize/"
    cancel_path = f"/api/v1/checkout/sessions/{session.pk}/cancel/"
    assert (
        other_client.post(
            finalize_path,
            {"idempotencyKey": str(uuid4())},
            content_type="application/json",
        ).status_code
        == 404
    )
    assert other_client.post(cancel_path, content_type="application/json").status_code == 404


def test_cancel_checkout_releases_reservation_and_is_idempotent() -> None:
    user, _address, _variant, _method, session = prepare_checkout(
        email="cancel@example.com",
        slug="cancel",
    )
    reservation = InventoryReservation.objects.get(checkout_line__checkout=session)
    assert reservation.status == InventoryReservation.Status.ACTIVE

    cancelled = cancel_checkout(user, session.pk)
    cancelled_again = cancel_checkout(user, session.pk)
    reservation.refresh_from_db()

    assert cancelled.status == CheckoutSession.Status.CANCELLED
    assert cancelled_again.status == CheckoutSession.Status.CANCELLED
    assert reservation.status == InventoryReservation.Status.RELEASED


def test_finalize_is_idempotent_and_leaves_reservation_for_b06_handoff() -> None:
    user, _address, variant, _method, session = prepare_checkout(
        email="finalize@example.com",
        slug="finalize",
        quantity=2,
        stock=5,
    )
    inventory = VariantInventory.objects.get(variant=variant)
    original_on_hand = inventory.on_hand
    key = uuid4()

    ready = finalize_checkout(user, session.pk, idempotency_key=key)
    replay = finalize_checkout(user, session.pk, idempotency_key=key)
    reservation = InventoryReservation.objects.get(checkout_line__checkout=session)
    inventory.refresh_from_db()

    assert ready.status == CheckoutSession.Status.READY
    assert replay.pk == ready.pk
    assert replay.finalization_key == key
    assert reservation.status == InventoryReservation.Status.ACTIVE
    assert inventory.on_hand == original_on_hand

    with pytest.raises(CheckoutConflictError):
        finalize_checkout(user, session.pk, idempotency_key=uuid4())


def test_finalization_key_is_scoped_to_user_not_global() -> None:
    shared_key = uuid4()
    first_user, _address1, _variant1, _method1, first = prepare_checkout(
        email="final-key-a@example.com",
        slug="final-key-a",
    )
    finalize_checkout(first_user, first.pk, idempotency_key=shared_key)

    second_user = create_user("final-key-b@example.com")
    second_address = create_address(second_user)
    second_variant = create_sellable_variant(slug="final-key-b")
    add_cart_line(second_user, second_variant.id, quantity=1)
    second = create_checkout(
        second_user,
        address_id=second_address.pk,
        shipping_method_code="standard",
        idempotency_key=uuid4(),
    )

    second_ready = finalize_checkout(second_user, second.pk, idempotency_key=shared_key)
    assert second_ready.status == CheckoutSession.Status.READY


def test_finalize_rejects_cart_revision_price_and_address_drift() -> None:
    user, address, variant, _method, session = prepare_checkout(
        email="stale-cart@example.com",
        slug="stale-cart",
        quantity=1,
        stock=5,
    )
    add_cart_line(user, variant.id, quantity=1)
    with pytest.raises(CheckoutStaleError):
        finalize_checkout(user, session.pk, idempotency_key=uuid4())
    cancel_checkout(user, session.pk)

    session = create_checkout(
        user,
        address_id=address.pk,
        shipping_method_code="standard",
        idempotency_key=uuid4(),
    )
    VariantPrice.objects.filter(variant=variant).update(amount_toman=Decimal(210_000))
    with pytest.raises(CheckoutStaleError):
        finalize_checkout(user, session.pk, idempotency_key=uuid4())
    cancel_checkout(user, session.pk)

    session = create_checkout(
        user,
        address_id=address.pk,
        shipping_method_code="standard",
        idempotency_key=uuid4(),
    )
    Address.objects.filter(pk=address.pk).update(address_line1="Changed after validation")
    with pytest.raises(CheckoutStaleError):
        finalize_checkout(user, session.pk, idempotency_key=uuid4())


def test_expired_checkout_is_terminated_and_reservation_is_not_active() -> None:
    user, _address, _variant, _method, session = prepare_checkout(
        email="expiry@example.com",
        slug="expiry",
    )
    after_expiry = session.expires_at + timedelta(seconds=1)

    assert get_current_checkout(user, at=after_expiry) is None
    session.refresh_from_db()
    reservation = InventoryReservation.objects.get(checkout_line__checkout=session)

    assert session.status == CheckoutSession.Status.EXPIRED
    assert reservation.status != InventoryReservation.Status.ACTIVE


def test_shipping_options_api_is_authenticated_and_user_scoped() -> None:
    user = create_user("shipping-api@example.com")
    address = create_address(user)
    variant = create_sellable_variant(slug="shipping-api")
    configure_checkout_policy()
    add_cart_line(user, variant.id, quantity=1)

    anonymous = Client()
    assert anonymous.get(SHIPPING_OPTIONS_PATH, {"addressId": address.pk}).status_code in {401, 403}

    client = authenticated_client(user)
    response = client.get(SHIPPING_OPTIONS_PATH, {"addressId": address.pk})
    assert response.status_code == 200
    assert response.json()["options"][0]["method"]["code"] == "standard"


def test_concurrent_checkouts_cannot_oversell_shared_inventory() -> None:
    variant = create_sellable_variant(slug="concurrent-checkout", stock=1, price=100_000)
    configure_checkout_policy(flat_rate=0, tax_rate_bps=0)

    first_user = create_user("concurrent-a@example.com")
    second_user = create_user("concurrent-b@example.com")
    first_address = create_address(first_user, label="A")
    second_address = create_address(second_user, label="B")
    add_cart_line(first_user, variant.id, quantity=1)
    add_cart_line(second_user, variant.id, quantity=1)

    def attempt(user_id: int, address_id: int, key: UUID) -> str:
        close_old_connections()
        try:
            user = User.objects.get(pk=user_id)
            create_checkout(
                user,
                address_id=address_id,
                shipping_method_code="standard",
                idempotency_key=key,
            )
        except CheckoutUnavailableError:
            return "unavailable"
        finally:
            close_old_connections()
        return "success"

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda args: attempt(*args),
                [
                    (first_user.pk, first_address.pk, uuid4()),
                    (second_user.pk, second_address.pk, uuid4()),
                ],
            )
        )

    assert sorted(results) == ["success", "unavailable"]
    assert (
        InventoryReservation.objects.filter(status=InventoryReservation.Status.ACTIVE).count() == 1
    )
    assert CheckoutSession.objects.filter(status=CheckoutSession.Status.ACTIVE).count() == 1
    inventory = VariantInventory.objects.get(variant=variant)
    assert inventory.on_hand == 1
