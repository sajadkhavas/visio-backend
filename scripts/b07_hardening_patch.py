from pathlib import Path

services = Path("apps/payments/services.py")
text = services.read_text()
text = text.replace(
    "from apps.accounts.models import User\nfrom apps.orders.models import Order\n",
    "from apps.accounts.models import User\nfrom apps.commerce.services import InventoryUnavailableError, ReservationStateError\nfrom apps.orders.models import Order\n",
    1,
)
text = text.replace(
    "            if existing.status == PaymentAttempt.Status.VERIFIED:\n                return existing, False\n\n        if order.status != Order.Status.PENDING_PAYMENT:",
    "            if existing.status == PaymentAttempt.Status.VERIFIED:\n                return existing, False\n            if existing.status == PaymentAttempt.Status.REQUESTING:\n                raise PaymentConflictError(\"Payment request is already in progress.\")\n\n        if order.status != Order.Status.PENDING_PAYMENT:",
    1,
)
text = text.replace(
    "        if attempt.status == PaymentAttempt.Status.VERIFIED:\n            return _verified_outcome(attempt)\n        if not attempt.provider_authority:",
    "        if attempt.status == PaymentAttempt.Status.VERIFIED:\n            return _verified_outcome(attempt)\n        if attempt.status == PaymentAttempt.Status.VERIFYING:\n            raise PaymentConflictError(\"Payment verification is already in progress.\")\n        if not attempt.provider_authority:",
    1,
)
text = text.replace(
    "            PaymentAttempt.Status.PENDING,\n            PaymentAttempt.Status.VERIFYING,\n            PaymentAttempt.Status.FAILED,",
    "            PaymentAttempt.Status.PENDING,\n            PaymentAttempt.Status.FAILED,",
    1,
)
old = '''def _apply_verified_result(
    attempt_id: UUID,
    result: ProviderVerifyResult,
    *,
    at: datetime,
) -> PaymentVerificationOutcome:
    with transaction.atomic():
        attempt = (
            PaymentAttempt.objects.select_for_update().select_related("order").get(pk=attempt_id)
        )
        if attempt.status == PaymentAttempt.Status.VERIFIED:
            return _verified_outcome(attempt)

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
            confirmed_order = confirm_order_after_verified_payment(order.id, at=at)
        except OrderError as exc:
            PaymentReconciliation.objects.create(
                attempt=attempt,
                status=PaymentReconciliation.Status.MISMATCH,
                provider_code=result.code,
                provider_ref_id=result.ref_id,
                provider_payload_digest=digest,
                detail=f"Verified provider payment could not confirm order: {exc}"[:500],
                checked_at=at,
            )
            attempt.order = order
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
        attempt.order = confirmed_order
        return PaymentVerificationOutcome(
            attempt=attempt,
            order_confirmed=True,
            reconciliation_required=False,
        )
'''
new = '''def _apply_verified_result(
    attempt_id: UUID,
    result: ProviderVerifyResult,
    *,
    at: datetime,
) -> PaymentVerificationOutcome:
    digest = _digest_verify(result)

    # Provider truth must survive any later order/inventory mismatch.
    with transaction.atomic():
        attempt = (
            PaymentAttempt.objects.select_for_update().select_related("order").get(pk=attempt_id)
        )
        if attempt.status == PaymentAttempt.Status.VERIFIED:
            return _verified_outcome(attempt)
        order = Order.objects.select_for_update().get(pk=attempt.order_id)
        amount_matches = int(attempt.amount_rial) == int(order.payable_toman) * 10
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
        order_id = order.id

    with transaction.atomic():
        attempt = (
            PaymentAttempt.objects.select_for_update().select_related("order").get(pk=attempt_id)
        )
        order = Order.objects.select_for_update().get(pk=order_id)
        if not amount_matches:
            PaymentReconciliation.objects.create(
                attempt=attempt,
                status=PaymentReconciliation.Status.MISMATCH,
                provider_code=result.code,
                provider_ref_id=result.ref_id,
                provider_payload_digest=digest,
                detail="Verified provider amount does not match server-authoritative order amount.",
                checked_at=at,
            )
            attempt.order = order
            return PaymentVerificationOutcome(
                attempt=attempt,
                order_confirmed=False,
                reconciliation_required=True,
            )
        try:
            confirmed_order = confirm_order_after_verified_payment(order.id, at=at)
        except (OrderError, InventoryUnavailableError, ReservationStateError) as exc:
            PaymentReconciliation.objects.create(
                attempt=attempt,
                status=PaymentReconciliation.Status.MISMATCH,
                provider_code=result.code,
                provider_ref_id=result.ref_id,
                provider_payload_digest=digest,
                detail=f"Verified provider payment could not confirm order: {exc}"[:500],
                checked_at=at,
            )
            attempt.order = order
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
        attempt.order = confirmed_order
        return PaymentVerificationOutcome(
            attempt=attempt,
            order_confirmed=True,
            reconciliation_required=False,
        )
'''
if old not in text:
    raise SystemExit("EXPECTED_APPLY_BLOCK_NOT_FOUND")
services.write_text(text.replace(old, new, 1))

models = Path("apps/payments/models.py")
text = models.read_text()
needle = '''            models.UniqueConstraint(
                fields=("provider", "provider_authority"),
                condition=~models.Q(provider_authority=""),
                name="payments_provider_authority_unique",
            ),
'''
addition = needle + '''            models.UniqueConstraint(
                fields=("order",),
                condition=models.Q(
                    status__in=("requesting", "pending", "verifying", "verified")
                ),
                name="payments_one_active_attempt_per_order",
            ),
'''
if needle not in text:
    raise SystemExit("EXPECTED_CONSTRAINT_BLOCK_NOT_FOUND")
models.write_text(text.replace(needle, addition, 1))
