from __future__ import annotations

from datetime import datetime
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User

from .models import CheckoutSession
from .services import CheckoutConflictError, CheckoutNotFoundError, _revalidate_ready_boundary


def revalidate_ready_checkout(
    user: User,
    checkout_id: UUID,
    *,
    at: datetime | None = None,
) -> CheckoutSession:
    """B06 bridge: lock and fully revalidate a B05 READY checkout inside caller transaction."""

    now = at or timezone.now()
    with transaction.atomic():
        User.objects.select_for_update().only("pk").get(pk=user.pk)
        try:
            session = (
                CheckoutSession.objects.select_for_update()
                .select_related("shipping_method", "shipping_method__zone")
                .get(pk=checkout_id, user=user)
            )
        except CheckoutSession.DoesNotExist as exc:
            raise CheckoutNotFoundError("Checkout session does not exist for this user.") from exc

        if session.status != CheckoutSession.Status.READY:
            raise CheckoutConflictError("Only a READY checkout can create an order.")

        _revalidate_ready_boundary(user, session, at=now)
        return session
