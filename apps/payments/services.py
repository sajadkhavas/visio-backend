from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.orders.models import Order
from apps.orders.services import OrderTransitionError, confirm_order_after_verified_payment

from .models import PaymentAttempt, PaymentReconciliation
from .providers import (
    PaymentProvider,
    ProviderConfigurationError,
    ProviderError,
    ProviderRequestResult,
    ProviderVerifyResult,
    ZarinPalProvider,
)


class PaymentError(Exception):
    """Base class for B07 payment-domain failures."""


class PaymentNotFoundError(PaymentError):
    pass


class PaymentConflictError(PaymentError):
    pass


class PaymentConfigurationError(PaymentError):
    pass


class PaymentProviderError(PaymentError):
    pass


@dataclass(frozen=True)
class PaymentStartResult:
    attempt: PaymentAttempt
    redirect_url: str
    created: bool


@dataclass(frozen=True)
class PaymentVerificationOutcome:
    attempt: PaymentAttempt
    order_confirmed: bool
    reconciliation_required: bool


def _provider_from_settings() -> PaymentProvider:
    if not settings.PAYMENTS_ENABLED:
        raise PaymentConfigurationError("Payments are disabled.")
    if settings.PAYMENT_PROVIDER != PaymentAttempt.Provider.ZARINPAL:
        raise PaymentConfigurationError("Configured payment provider is unsupported.")
    try:
        return ZarinPalProvider(
            merchant_id=settings.ZARINPAL_MERCHANT_ID,
            sandbox=settings.ZARINPAL_SANDBOX,
            timeout_seconds=settings.PAYMENT_PROVIDER_TIMEOUT_SECONDS,
            access_token=settings.ZARINPAL_ACCESS_TOKEN,
        )
    except ProviderConfigurationError as exc:
        raise PaymentConfigurationError(str(exc)) from exc


def _provider(provider: PaymentProvider | None) -> PaymentProvider:
    return provider if provider is not None else _provider_from_settings()


def _amounts(order: Order) -> tuple[int, int]:
    amount_toman = int(order.payable_toman)
    amount_rial = amount_toman * 10
    if amount_toman < 0:
        raise PaymentConflictError("Order payable amount cannot be negative.")
    if amount_rial < 1_000:
        raise PaymentConflictError("Order payable amount is below the provider minimum.")
    return amount_toman, amount_rial


def _digest_verify(result: ProviderVerifyResult) -> str:
    canonical = json.dumps(
        {
            "code": result.code,
            "message": result.message,
            "refId": result.ref_id,
            "maskedCard": result.masked_card,
            "cardHash": result.card_hash,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _locked_owned_order(user: User, public_id: UUID) -> Order:
    try:
        return Order.objects.select_for_update().get(user=user, public_id=public_id)
    except Order.DoesNotExist as exc:
        raise PaymentNotFoundError("Order does not exist for this user.") from exc


def _active_attempt_for_order(order: Order) -> PaymentAttempt | None:
    return (
        PaymentAttempt.objects.select_for_update()
        .filter(
            order=order,
            status__in=(
                PaymentAttempt.Status.REQUESTING,
                PaymentAttempt.Status.PENDING,
                PaymentAttempt.Status.VERIFYING,
                PaymentAttempt.Status.VERIFIED,
            ),
        )
        .order_by("created_at", "id")
        .first()
    )


def _prepare_attempt(
    user: User,
    *,
    order_public_id: UUID,
    idempotency_key: UUID,
    provider_name: str,
    at: datetime,
) -> tuple[PaymentAttempt, bool]:
    with transaction.atomic():
        User.objects.select_for_update().only("pk").get(pk=user.pk)
        order = _locked_owned_order(user, order_public_id)
        if order.status != Order.Status.PENDING_PAYMENT:
            raise PaymentConflictError("Only a pending-payment order can start a payment.")

        existing = (
            PaymentAttempt.objects.select_for_update()
            .filter(order=order, idempotency_key=idempotency_key)
            .first()
        )
        if existing is not None:
            if existing.provider != provider_name:
                raise PaymentConflictError("Payment idempotency key belongs to another provider.")
            if existing.status == PaymentAttempt.Status.VERIFIED:
                return existing, False
            if existing.provider_authority and existing.status in {
                PaymentAttempt.Status.PENDING,
                PaymentAttempt.Status.VERIFYING,
            }:
                return existing, False
            existing.status = PaymentAttempt.Status.REQUESTING
            existing.request_count += 1
            existing.status_changed_at = at
            existing.updated_at = at
            existing.save(
                update_fields=("status", "request_count", "status_changed_at", "updated_at")
            )
            return existing, False

        active = _active_attempt_for_order(order)
        if active is not None:
            raise PaymentConflictError("This order already has an active payment attempt.")

        amount_toman, amount_rial = _amounts(order)
        try:
            attempt = PaymentAttempt.objects.create(
                order=order,
                idempotency_key=idempotency_key,
                provider=provider_name,
                status=PaymentAttempt.Status.REQUESTING,
                amount_toman=amount_toman,
                amount_rial=amount_rial,
                request_count=1,
                status_changed_at=at,
            )
        except IntegrityError as exc:
            raise PaymentConflictError("Concurrent payment attempt creation conflicted.") from exc
        return attempt, True


def _mark_request_failure(attempt_id: UUID, exc: ProviderError, *, at: datetime) -> None:
    with transaction.atomic():
        attempt = PaymentAttempt.objects.select_for_update().get(pk=attempt_id)
        if attempt.provider_authority:
            return
        attempt.status = PaymentAttempt.Status.FAILED
        attempt.provider_message = str(exc)[:500]
        attempt.status_changed_at = at
        attempt.updated_at = at
        attempt.save(
            update_fields=(
                "status",
                "provider_message",
                "status_changed_at",
                "updated_at",
            )
        )


def _record_request_success(
    attempt_id: UUID,
    result: ProviderRequestResult,
    *,
    at: datetime,
) -> PaymentAttempt:
    with transaction.atomic():
        attempt = PaymentAttempt.objects.select_for_update().get(pk=attempt_id)
        if attempt.provider_authority:
            return attempt
        attempt.provider_authority = result.authority
        attempt.provider_redirect_url = result.redirect_url
        attempt.provider_code = result.code
        attempt.provider_message = result.message[:500]
        attempt.status = PaymentAttempt.Status.PENDING
        attempt.status_changed_at = at
        attempt.updated_at = at
        attempt.save(
            update_fields=(
                "provider_authority",
                "provider_redirect_url",
                "provider_code",
                "provider_message",
                "status",
                "status_changed_at",
                "updated_at",
            )
        )
        return attempt


def start_payment(
    user: User,
    *,
    order_public_id: UUID,
    idempotency_key: UUID,
    provider: PaymentProvider | None = None,
    at: datetime | None = None,
) -> PaymentStartResult:
    now = at or timezone.now()
    payment_provider = _provider(provider)
    attempt, created = _prepare_attempt(
        user,
        order_public_id=order_public_id,
        idempotency_key=idempotency_key,
        provider_name=payment_provider.name,
        at=now,
    )
    if attempt.provider_authority and attempt.provider_redirect_url:
        return PaymentStartResult(
            attempt=attempt,
            redirect_url=attempt.provider_redirect_url,
            created=False,
        )
    if attempt.status == PaymentAttempt.Status.VERIFIED:
        return PaymentStartResult(attempt=attempt, redirect_url="", created=False)

    try:
        result = payment_provider.request_payment(
            amount_rial=int(attempt.amount_rial),
            callback_url=settings.PAYMENT_CALLBACK_URL,
            description=f"VISIO order {attempt.order.public_id}",
            email=attempt.order.user.email,
        )
    except ProviderError as exc:
        _mark_request_failure(attempt.id, exc, at=timezone.now())
        raise PaymentProviderError(str(exc)) from exc

    attempt = _record_request_success(attempt.id, result, at=timezone.now())
    return PaymentStartResult(attempt=attempt, redirect_url=attempt.provider_redirect_url, created=created)


def _record_provider_error(attempt_id: UUID, exc: ProviderError, *, at: datetime) -> None:
    with transaction.atomic():
        attempt = PaymentAttempt.objects.select_for_update().get(pk=attempt_id)
        attempt.status = PaymentAttempt.Status.FAILED
        attempt.provider_message = str(exc)[:500]
        attempt.status_changed_at = at
        attempt.updated_at = at
        attempt.save(
            update_fields=("status", "provider_message", "status_changed_at", "updated_at")
        )
        PaymentReconciliation.objects.create(
            attempt=attempt,
            status=PaymentReconciliation.Status.PROVIDER_ERROR,
            provider_payload_digest=hashlib.sha256(str(exc).encode("utf-8")).hexdigest(),
            detail=str(exc)[:500],
            checked_at=at,
        )


def _apply_verified_result(
    attempt_id: UUID,
    result: ProviderVerifyResult,
    *,
    at: datetime,
) -> PaymentVerificationOutcome:
    with transaction.atomic():
        attempt = PaymentAttempt.objects.select_for_update().select_related("order").get(pk=attempt_id)
        if attempt.status == PaymentAttempt.Status.VERIFIED:
            return PaymentVerificationOutcome(
                attempt=attempt,
                order_confirmed=attempt.order.status != Order.Status.PENDING_PAYMENT,
                reconciliation_required=False,
            )

        order = Order.objects.select_for_update().get(pk=attempt.order_id)
        expected_rial = int(order.payable_toman) * 10
        if int(attempt.amount_rial) != expected_rial:
            raise PaymentConflictError("Payment amount no longer matches immutable order truth.")

        attempt.status = PaymentAttempt.Status.VERIFIED
        attempt.provider_code = result.code
        attempt.provider_message = result.message[:500]
        attempt.provider_ref_id = result.ref_id
        attempt.masked_card = result.masked_card[:32]
        attempt.card_hash = result.card_hash[:128]
        attempt.verified_at = at
        attempt.status_changed_at = at
        attempt.updated_at = at
        attempt.save(
            update_fields=(
                "status",
                "provider_code",
                "provider_message",
                "provider_ref_id",
                "masked_card",
                "card_hash",
                "verified_at",
                "status_changed_at",
                "updated_at",
            )
        )

        digest = _digest_verify(result)
        try:
            confirm_order_after_verified_payment(order.id, at=at)
        except OrderTransitionError as exc:
            PaymentReconciliation.objects.create(
                attempt=attempt,
                status=PaymentReconciliation.Status.MISMATCH,
                provider_code=result.code,
                provider_ref_id=result.ref_id,
                provider_payload_digest=digest,
                detail=f"Verified provider payment could not confirm order: {exc}"[:500],
                checked_at=at,
            )
            return PaymentVerificationOutcome(
                attempt=attempt,
                order_confirmed=False,
                reconciliation_required=True,
            )

        PaymentReconciliation.objects.create(
            attempt=attempt,
            status=PaymentReconciliation.Status.MATCHED,
            provider_code=result.code,
            provider_ref_id=result.ref_id,
            provider_payload_digest=digest,
            detail="Provider verification matches server-authoritative order amount.",
            checked_at=at,
        )
        return PaymentVerificationOutcome(
            attempt=attempt,
            order_confirmed=True,
            reconciliation_required=False,
        )


def verify_attempt(
    attempt_id: UUID,
    *,
    provider: PaymentProvider | None = None,
    at: datetime | None = None,
) -> PaymentVerificationOutcome:
    payment_provider = _provider(provider)
    now = at or timezone.now()
    with transaction.atomic():
        attempt = PaymentAttempt.objects.select_for_update().get(pk=attempt_id)
        if attempt.provider != payment_provider.name:
            raise PaymentConflictError("Payment attempt belongs to another provider.")
        if attempt.status == PaymentAttempt.Status.VERIFIED:
            order_confirmed = attempt.order.status != Order.Status.PENDING_PAYMENT
            return PaymentVerificationOutcome(
                attempt=attempt,
                order_confirmed=order_confirmed,
                reconciliation_required=False,
            )
        if not attempt.provider_authority:
            raise PaymentConflictError("Payment attempt has no provider authority.")
        if attempt.status not in {
            PaymentAttempt.Status.PENDING,
            PaymentAttempt.Status.VERIFYING,
            PaymentAttempt.Status.FAILED,
        }:
            raise PaymentConflictError(f"Payment in state {attempt.status!r} cannot be verified.")
        attempt.status = PaymentAttempt.Status.VERIFYING
        attempt.verify_count += 1
        attempt.status_changed_at = now
        attempt.updated_at = now
        attempt.save(
            update_fields=("status", "verify_count", "status_changed_at", "updated_at")
        )
        amount_rial = int(attempt.amount_rial)
        authority = attempt.provider_authority

    try:
        result = payment_provider.verify_payment(amount_rial=amount_rial, authority=authority)
    except ProviderError as exc:
        _record_provider_error(attempt_id, exc, at=timezone.now())
        raise PaymentProviderError(str(exc)) from exc
    return _apply_verified_result(attempt_id, result, at=timezone.now())


def process_callback(
    *,
    authority: str,
    callback_status: str,
    provider: PaymentProvider | None = None,
    at: datetime | None = None,
) -> PaymentVerificationOutcome:
    payment_provider = _provider(provider)
    now = at or timezone.now()
    with transaction.atomic():
        try:
            attempt = PaymentAttempt.objects.select_for_update().select_related("order").get(
                provider=payment_provider.name,
                provider_authority=authority,
            )
        except PaymentAttempt.DoesNotExist as exc:
            raise PaymentNotFoundError("Payment authority is unknown.") from exc
        attempt.callback_count += 1
        attempt.last_callback_status = callback_status[:32]
        attempt.updated_at = now
        attempt.save(update_fields=("callback_count", "last_callback_status", "updated_at"))
        if attempt.status == PaymentAttempt.Status.VERIFIED:
            return PaymentVerificationOutcome(
                attempt=attempt,
                order_confirmed=attempt.order.status != Order.Status.PENDING_PAYMENT,
                reconciliation_required=False,
            )
        if callback_status.upper() != "OK":
            if attempt.status in {PaymentAttempt.Status.PENDING, PaymentAttempt.Status.VERIFYING}:
                attempt.status = PaymentAttempt.Status.CANCELLED
                attempt.status_changed_at = now
                attempt.save(update_fields=("status", "status_changed_at"))
            return PaymentVerificationOutcome(
                attempt=attempt,
                order_confirmed=False,
                reconciliation_required=False,
            )

    return verify_attempt(attempt.id, provider=payment_provider, at=now)


def reconcile_attempt(
    attempt_id: UUID,
    *,
    provider: PaymentProvider | None = None,
    at: datetime | None = None,
) -> PaymentVerificationOutcome:
    """Authoritative recovery path for missed/duplicated callbacks."""

    return verify_attempt(attempt_id, provider=provider, at=at)


def reconciliation_summary(attempt: PaymentAttempt) -> dict[str, Any]:
    latest = attempt.reconciliations.order_by("-checked_at", "id").first()
    if latest is None:
        return {"status": "not_checked"}
    return {
        "status": latest.status,
        "providerCode": latest.provider_code,
        "providerRefId": latest.provider_ref_id,
        "detail": latest.detail,
        "checkedAt": latest.checked_at.isoformat(),
    }
