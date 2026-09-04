from __future__ import annotations

from uuid import UUID

from django.db.models import QuerySet

from apps.accounts.models import User

from .models import Order
from .services import OrderNotFoundError


def orders_for_user(user: User) -> QuerySet[Order]:
    return Order.objects.filter(user=user).prefetch_related("lines").order_by("-created_at", "id")


def order_for_user(user: User, public_id: UUID) -> Order:
    try:
        return (
            Order.objects.filter(user=user)
            .prefetch_related("lines")
            .get(public_id=public_id)
        )
    except Order.DoesNotExist as exc:
        raise OrderNotFoundError("Order does not exist for this user.") from exc
