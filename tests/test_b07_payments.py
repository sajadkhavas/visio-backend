from __future__ import annotations

from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from apps.accounts.models import Address, User
from apps.cart.services import add_cart_line
from apps.catalog.models import Brand, Category, Product, ProductVariant
from apps.checkout.models import CheckoutTaxPolicy, ShippingMethod, ShippingZone
from apps.checkout.services import create_checkout, finalize_checkout
from apps.commerce.models import InventoryReservation, VariantInventory, VariantPrice
from apps.orders.models import Order
from apps.orders.services import cancel_order, create_order
from apps.payments.models import PaymentAttempt, PaymentReconciliation
from apps.payments.providers import (
    ProviderRejectedError,
    ProviderRequestResult,
    ProviderVerifyResult,
)
from apps.payments.services import (
    PaymentConflictError,
    PaymentProviderError,
    process_callback,
    reconcile_attempt,
    start_payment,
)
from django.db import IntegrityError, transaction
from django.test import Client
from django.utils import timezone

pytestmark = pytest.mark.django_db(transaction=True)


class FakeProvider:
    name = "zarinpal"

    def __init__(self) -> None:
        self.request_calls: list[dict[str, object]] = []
        self.verify_calls: list[dict[str, object]] = []
        self.verify_error: Exception | None = None
        self.authority = "A12345678901234567890123456789012345"
        self.ref_id = "REF-100200300"

    def request_payment(
        self,
        *,
        amount_rial: int,
        callback_url: str,
        description: str,
        mobile: str = "",
        email: str = "",
    ) -> ProviderRequestResult:
        self.request_calls.append(
            {
                "amount_rial": amount_rial,
                "callback_url": callback_url,
                "description": description,
                "mobile": mobile,
                "email": email,
            }
        )
        return ProviderRequestResult(
            code=100,
            message="Success",
            authority=self.authority,
            redirect_url=f"https://payment.zarinpal.com/pg/StartPay/{self.authority}",
        )

    def verify_payment(self, *, amount_rial: int, authority: str) -> ProviderVerifyResult:
        self.verify_calls.append({"amount_rial": amount_rial, "authority": authority})
        if self.verify_error is not None:
            raise self.verify_error
        return ProviderVerifyResult(
            code=100,
            message="Verified",
            ref_id=self.ref_id,
            masked_card="6037********1234",
            card_hash="card-hash-evidence",
        )

    def reverse_payment(self, *, authority: str) -> ProviderVerifyResult:
        return ProviderVerifyResult(code=100, message="Reversed", ref_id="")

    def refund_payment(
        self,
        *,
        session_id: str,
        amount_rial: int,
        description: str,
        reason: str,
    ) -> str:
        return "refund-1"


def create_user(email: str) -> User:
    return User.objects.create_user(
        username=email,
        email=email,
        password="Correct-Horse-Battery-44",
    )


def prepare_pending_order(*, email: str, slug: str) -> tuple[User, Order]:
    user = create_user(email)
    address = Address.objects.create(
        user=user,
        label="Home",
        recipient_name="Payment Customer",
        recipient_phone="+989121234567",
        country_code="IR",
        province="Tehran",
        city="Tehran",
        postal_code="1234567890",
        address_line1="Payment street",
        address_line2="",
    )
    zone = ShippingZone.objects.create(
        code=f"zone-{slug}",
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
    VariantPrice.objects.create(variant=variant, amount_toman=Decimal(200_000))
    VariantInventory.objects.create(variant=variant, on_hand=5)
    add_cart_line(user, variant.pk, quantity=1)
    checkout = create_checkout(
        user,
        address_id=address.pk,
        shipping_method_code=method.code,
        idempotency_key=uuid4(),
    )
    checkout = finalize_checkout(user, checkout.pk, idempotency_key=uuid4())
    order = create_order(user, checkout_id=checkout.pk, idempotency_key=uuid4()).order
    return user, order


def authenticated_client(user: User) -> Client:
    client = Client()
    client.force_login(user, backend="apps.accounts.backends.EmailAuthenticationBackend")
    return client


def test_payment_start_uses_exact_rial_conversion_and_is_idempotent(settings: object) -> None:
    user, order = prepare_pending_order(
        email="payment-start@example.com",
        slug="payment-start",
    )
    provider = FakeProvider()
    key = uuid4()
    settings.PAYMENT_CALLBACK_URL = "https://api.example.test/api/v1/payments/zarinpal/callback/"

    first = start_payment(
        user,
        order_public_id=order.public_id,
        idempotency_key=key,
        provider=provider,
    )
    replay = start_payment(
        user,
        order_public_id=order.public_id,
        idempotency_key=key,
        provider=provider,
    )

    assert first.created is True
    assert replay.created is False
    assert replay.attempt.id == first.attempt.id
    assert PaymentAttempt.objects.count() == 1
    assert len(provider.request_calls) == 1
    assert int(first.attempt.amount_rial) == int(first.attempt.amount_toman) * 10
    assert provider.request_calls[0]["amount_rial"] == int(order.payable_toman) * 10
    assert first.redirect_url.endswith(provider.authority)

    with pytest.raises(PaymentConflictError):
        start_payment(
            user,
            order_public_id=order.public_id,
            idempotency_key=uuid4(),
            provider=provider,
        )


def test_ok_callback_requires_provider_verify_and_duplicate_callback_is_idempotent(
    settings: object,
) -> None:
    user, order = prepare_pending_order(
        email="payment-verify@example.com",
        slug="payment-verify",
    )
    provider = FakeProvider()
    settings.PAYMENT_CALLBACK_URL = "https://api.example.test/api/v1/payments/zarinpal/callback/"
    started = start_payment(
        user,
        order_public_id=order.public_id,
        idempotency_key=uuid4(),
        provider=provider,
    )

    first = process_callback(
        authority=provider.authority,
        callback_status="OK",
        provider=provider,
    )
    duplicate = process_callback(
        authority=provider.authority,
        callback_status="OK",
        provider=provider,
    )

    order.refresh_from_db()
    started.attempt.refresh_from_db()
    reservation = InventoryReservation.objects.get(order_line__order=order)
    assert order.status == Order.Status.CONFIRMED
    assert reservation.status == InventoryReservation.Status.CONSUMED
    assert first.order_confirmed is True
    assert duplicate.order_confirmed is True
    assert started.attempt.status == PaymentAttempt.Status.VERIFIED
    assert started.attempt.provider_ref_id == provider.ref_id
    assert started.attempt.callback_count == 2
    assert started.attempt.verify_count == 1
    assert len(provider.verify_calls) == 1
    assert (
        PaymentReconciliation.objects.filter(
            attempt=started.attempt,
            status=PaymentReconciliation.Status.MATCHED,
        ).count()
        == 1
    )


def test_non_ok_callback_never_cancels_order_or_consumes_inventory(settings: object) -> None:
    user, order = prepare_pending_order(
        email="payment-cancelled@example.com",
        slug="payment-cancelled",
    )
    provider = FakeProvider()
    settings.PAYMENT_CALLBACK_URL = "https://api.example.test/api/v1/payments/zarinpal/callback/"
    started = start_payment(
        user,
        order_public_id=order.public_id,
        idempotency_key=uuid4(),
        provider=provider,
    )

    outcome = process_callback(
        authority=provider.authority,
        callback_status="NOK",
        provider=provider,
    )

    order.refresh_from_db()
    started.attempt.refresh_from_db()
    reservation = InventoryReservation.objects.get(order_line__order=order)
    assert outcome.order_confirmed is False
    assert order.status == Order.Status.PENDING_PAYMENT
    assert reservation.status == InventoryReservation.Status.ACTIVE
    assert started.attempt.status == PaymentAttempt.Status.CANCELLED
    assert len(provider.verify_calls) == 0


def test_forged_ok_callback_cannot_confirm_without_authoritative_verification(
    settings: object,
) -> None:
    user, order = prepare_pending_order(
        email="payment-forged@example.com",
        slug="payment-forged",
    )
    provider = FakeProvider()
    provider.verify_error = ProviderRejectedError("provider says not paid")
    settings.PAYMENT_CALLBACK_URL = "https://api.example.test/api/v1/payments/zarinpal/callback/"
    started = start_payment(
        user,
        order_public_id=order.public_id,
        idempotency_key=uuid4(),
        provider=provider,
    )

    with pytest.raises(PaymentProviderError):
        process_callback(
            authority=provider.authority,
            callback_status="OK",
            provider=provider,
        )

    order.refresh_from_db()
    started.attempt.refresh_from_db()
    assert order.status == Order.Status.PENDING_PAYMENT
    assert started.attempt.status == PaymentAttempt.Status.FAILED
    assert PaymentReconciliation.objects.filter(
        attempt=started.attempt,
        status=PaymentReconciliation.Status.PROVIDER_ERROR,
    ).exists()


def test_verified_payment_after_order_cancel_is_preserved_as_reconciliation_mismatch(
    settings: object,
) -> None:
    user, order = prepare_pending_order(
        email="payment-race@example.com",
        slug="payment-race",
    )
    provider = FakeProvider()
    settings.PAYMENT_CALLBACK_URL = "https://api.example.test/api/v1/payments/zarinpal/callback/"
    started = start_payment(
        user,
        order_public_id=order.public_id,
        idempotency_key=uuid4(),
        provider=provider,
    )
    cancel_order(user, order.public_id)

    outcome = reconcile_attempt(started.attempt.id, provider=provider)

    order.refresh_from_db()
    started.attempt.refresh_from_db()
    assert order.status == Order.Status.CANCELLED
    assert started.attempt.status == PaymentAttempt.Status.VERIFIED
    assert outcome.order_confirmed is False
    assert outcome.reconciliation_required is True
    assert PaymentReconciliation.objects.filter(
        attempt=started.attempt,
        status=PaymentReconciliation.Status.MISMATCH,
    ).exists()


def test_reconciliation_recovers_missed_callback_and_replay_after_verification_is_safe(
    settings: object,
) -> None:
    user, order = prepare_pending_order(
        email="payment-reconcile@example.com",
        slug="payment-reconcile",
    )
    provider = FakeProvider()
    key = uuid4()
    settings.PAYMENT_CALLBACK_URL = "https://api.example.test/api/v1/payments/zarinpal/callback/"
    started = start_payment(
        user,
        order_public_id=order.public_id,
        idempotency_key=key,
        provider=provider,
    )

    outcome = reconcile_attempt(started.attempt.id, provider=provider)
    replay = start_payment(
        user,
        order_public_id=order.public_id,
        idempotency_key=key,
        provider=provider,
    )

    order.refresh_from_db()
    assert outcome.order_confirmed is True
    assert order.status == Order.Status.CONFIRMED
    assert replay.attempt.id == started.attempt.id
    assert replay.attempt.status == PaymentAttempt.Status.VERIFIED
    assert len(provider.request_calls) == 1
    assert len(provider.verify_calls) == 1


def test_database_enforces_exact_toman_to_rial_contract(settings: object) -> None:
    user, order = prepare_pending_order(
        email="payment-money-db@example.com",
        slug="payment-money-db",
    )
    provider = FakeProvider()
    settings.PAYMENT_CALLBACK_URL = "https://api.example.test/api/v1/payments/zarinpal/callback/"
    attempt = start_payment(
        user,
        order_public_id=order.public_id,
        idempotency_key=uuid4(),
        provider=provider,
    ).attempt

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            PaymentAttempt.objects.filter(pk=attempt.pk).update(
                amount_rial=int(attempt.amount_rial) + 1
            )


def test_public_api_fails_closed_when_payments_are_disabled() -> None:
    user, order = prepare_pending_order(
        email="payment-disabled@example.com",
        slug="payment-disabled",
    )
    client = authenticated_client(user)

    response = client.post(
        "/api/v1/payments/",
        data={"orderId": str(order.public_id), "idempotencyKey": str(uuid4())},
        content_type="application/json",
    )

    assert response.status_code == 503
    assert PaymentAttempt.objects.count() == 0


def test_payment_detail_is_user_scoped(settings: object) -> None:
    owner, order = prepare_pending_order(
        email="payment-owner@example.com",
        slug="payment-owner",
    )
    provider = FakeProvider()
    settings.PAYMENT_CALLBACK_URL = "https://api.example.test/api/v1/payments/zarinpal/callback/"
    attempt = start_payment(
        owner,
        order_public_id=order.public_id,
        idempotency_key=uuid4(),
        provider=provider,
    ).attempt
    stranger = create_user("payment-stranger@example.com")
    client = authenticated_client(stranger)

    response = client.get(f"/api/v1/payments/{attempt.id}/")

    assert response.status_code == 404


def test_payment_attempt_ids_are_uuid_values(settings: object) -> None:
    user, order = prepare_pending_order(
        email="payment-uuid@example.com",
        slug="payment-uuid",
    )
    provider = FakeProvider()
    settings.PAYMENT_CALLBACK_URL = "https://api.example.test/api/v1/payments/zarinpal/callback/"
    attempt = start_payment(
        user,
        order_public_id=order.public_id,
        idempotency_key=uuid4(),
        provider=provider,
    ).attempt

    assert isinstance(attempt.id, UUID)
