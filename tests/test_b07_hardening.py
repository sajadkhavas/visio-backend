from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from apps.commerce.models import InventoryReservation
from apps.orders.models import Order
from apps.payments.models import PaymentAttempt, PaymentReconciliation
from apps.payments.providers import ProviderRequestResult, ProviderVerifyResult, ZarinPalProvider
from apps.payments.services import reconcile_attempt, start_payment
from django.db import IntegrityError, transaction
from tests.test_b07_payments import FakeProvider, prepare_pending_order

pytestmark = pytest.mark.django_db(transaction=True)


class RecordingZarinPalProvider(ZarinPalProvider):
    def __init__(self) -> None:
        super().__init__(merchant_id="merchant-test", access_token="access-test")
        self.calls: list[tuple[str, dict[str, Any], str]] = []

    def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
        *,
        authorization: str = "",
    ) -> dict[str, Any]:
        self.calls.append((url, payload, authorization))
        if url.endswith("/request.json"):
            return {
                "data": {
                    "code": 100,
                    "message": "Success",
                    "authority": "A12345678901234567890123456789012345",
                }
            }
        if url.endswith("/verify.json"):
            return {
                "data": {
                    "code": 100,
                    "message": "Verified",
                    "ref_id": 123456,
                    "card_pan": "6037********1234",
                    "card_hash": "hash",
                }
            }
        if url.endswith("/reverse.json"):
            return {"data": {"code": 100, "message": "Reversed", "ref_id": 123456}}
        return {"data": {"resource": {"id": "refund-1"}}}


def test_database_blocks_second_active_attempt_for_same_order(settings: Any) -> None:
    user, order = prepare_pending_order(
        email="payment-active-db@example.com",
        slug="payment-active-db",
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
            PaymentAttempt.objects.create(
                order=order,
                idempotency_key=uuid4(),
                provider=PaymentAttempt.Provider.ZARINPAL,
                status=PaymentAttempt.Status.REQUESTING,
                amount_toman=attempt.amount_toman,
                amount_rial=attempt.amount_rial,
            )


def test_verified_truth_survives_inventory_transition_failure(settings: Any) -> None:
    user, order = prepare_pending_order(
        email="payment-reservation-mismatch@example.com",
        slug="payment-reservation-mismatch",
    )
    provider = FakeProvider()
    settings.PAYMENT_CALLBACK_URL = "https://api.example.test/api/v1/payments/zarinpal/callback/"
    attempt = start_payment(
        user,
        order_public_id=order.public_id,
        idempotency_key=uuid4(),
        provider=provider,
    ).attempt
    reservation = InventoryReservation.objects.get(order_line__order=order)
    InventoryReservation.objects.filter(pk=reservation.pk).update(
        status=InventoryReservation.Status.EXPIRED
    )

    outcome = reconcile_attempt(attempt.id, provider=provider)

    attempt.refresh_from_db()
    order.refresh_from_db()
    assert attempt.status == PaymentAttempt.Status.VERIFIED
    assert order.status == Order.Status.PENDING_PAYMENT
    assert outcome.order_confirmed is False
    assert outcome.reconciliation_required is True
    assert PaymentReconciliation.objects.filter(
        attempt=attempt,
        status=PaymentReconciliation.Status.MISMATCH,
    ).exists()


def test_verified_amount_mismatch_is_recorded_without_confirming_order(settings: Any) -> None:
    user, order = prepare_pending_order(
        email="payment-amount-mismatch@example.com",
        slug="payment-amount-mismatch",
    )
    provider = FakeProvider()
    settings.PAYMENT_CALLBACK_URL = "https://api.example.test/api/v1/payments/zarinpal/callback/"
    attempt = start_payment(
        user,
        order_public_id=order.public_id,
        idempotency_key=uuid4(),
        provider=provider,
    ).attempt
    Order.objects.filter(pk=order.pk).update(
        subtotal_toman=order.subtotal_toman + 1_000,
        payable_toman=order.payable_toman + 1_000,
    )

    outcome = reconcile_attempt(attempt.id, provider=provider)

    attempt.refresh_from_db()
    order.refresh_from_db()
    assert attempt.status == PaymentAttempt.Status.VERIFIED
    assert order.status == Order.Status.PENDING_PAYMENT
    assert outcome.order_confirmed is False
    assert outcome.reconciliation_required is True
    assert PaymentReconciliation.objects.filter(
        attempt=attempt,
        status=PaymentReconciliation.Status.MISMATCH,
    ).exists()


def test_zarinpal_adapter_matches_official_v4_routes_and_irr_amount() -> None:
    provider = RecordingZarinPalProvider()
    authority = "A12345678901234567890123456789012345"

    request: ProviderRequestResult = provider.request_payment(
        amount_rial=1_000,
        callback_url="https://api.example.test/callback/",
        description="VISIO payment",
    )
    verify: ProviderVerifyResult = provider.verify_payment(amount_rial=1_000, authority=authority)
    reverse: ProviderVerifyResult = provider.reverse_payment(authority=authority)
    refund_id = provider.refund_payment(
        session_id="session-1",
        amount_rial=1_000,
        description="refund",
        reason="CUSTOMER_REQUEST",
    )

    assert provider.calls[0][0] == "https://payment.zarinpal.com/pg/v4/payment/request.json"
    assert provider.calls[0][1]["amount"] == 1_000
    assert provider.calls[1][0] == "https://payment.zarinpal.com/pg/v4/payment/verify.json"
    assert provider.calls[1][1]["amount"] == 1_000
    assert provider.calls[2][0] == "https://payment.zarinpal.com/pg/v4/payment/reverse.json"
    assert provider.calls[3][0] == "https://next.zarinpal.com/api/v4/graphql/"
    assert provider.calls[3][2] == "access-test"
    assert request.redirect_url == f"https://payment.zarinpal.com/pg/StartPay/{authority}"
    assert verify.ref_id == "123456"
    assert reverse.code == 100
    assert refund_id == "refund-1"
