from __future__ import annotations

from uuid import UUID

from apps.accounts.models import User

from .models import PaymentAttempt
from .services import PaymentNotFoundError


def payment_attempt_for_user(user: User, attempt_id: UUID) -> PaymentAttempt:
    try:
        return (
            PaymentAttempt.objects.filter(order__user=user)
            .select_related("order")
            .prefetch_related("reconciliations")
            .get(pk=attempt_id)
        )
    except PaymentAttempt.DoesNotExist as exc:
        raise PaymentNotFoundError("Payment attempt does not exist for this user.") from exc
