from __future__ import annotations

from typing import Any

from rest_framework import serializers

from .models import PaymentAttempt
from .services import reconciliation_summary


class PaymentStartSerializer(serializers.Serializer):
    orderId = serializers.UUIDField()
    idempotencyKey = serializers.UUIDField()


class PaymentCallbackSerializer(serializers.Serializer):
    Authority = serializers.CharField(max_length=64)
    Status = serializers.CharField(max_length=32)


def payment_payload(attempt: PaymentAttempt) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(attempt.id),
        "orderId": str(attempt.order.public_id),
        "provider": attempt.provider,
        "status": attempt.status,
        "amountToman": int(attempt.amount_toman),
        "amountRial": int(attempt.amount_rial),
        "currencyCode": attempt.currency_code,
        "displayUnit": attempt.display_unit,
        "authority": attempt.provider_authority,
        "referenceId": attempt.provider_ref_id,
        "maskedCard": attempt.masked_card,
        "requestCount": attempt.request_count,
        "callbackCount": attempt.callback_count,
        "verifyCount": attempt.verify_count,
        "verifiedAt": attempt.verified_at.isoformat() if attempt.verified_at else None,
        "createdAt": attempt.created_at.isoformat(),
        "updatedAt": attempt.updated_at.isoformat(),
        "reconciliation": reconciliation_summary(attempt),
    }
    if attempt.status == PaymentAttempt.Status.PENDING:
        payload["redirectUrl"] = attempt.provider_redirect_url
    return payload
