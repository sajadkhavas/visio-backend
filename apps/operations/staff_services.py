from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID

from django.core.exceptions import PermissionDenied
from django.db import transaction

from apps.accounts.models import User
from apps.catalog.models import ProductVariant
from apps.commerce.models import VariantInventory, VariantPrice
from apps.commerce.services import set_on_hand
from apps.orders.models import Order
from apps.orders.services import advance_fulfillment

from .audit import append_audit_event


def require_staff_permission(actor: User, permission: str) -> None:
    if not actor.is_active or not actor.is_staff or not actor.has_perm(permission):
        raise PermissionDenied(f"Missing staff permission: {permission}")


def advance_order_as_staff(
    actor: User,
    *,
    order_id: UUID,
    target_status: str,
) -> Order:
    require_staff_permission(actor, "orders.change_order")
    with transaction.atomic():
        before = Order.objects.select_for_update().get(pk=order_id)
        previous_status = before.status
        order = advance_fulfillment(order_id, target_status=target_status)
        if order.status != previous_status:
            append_audit_event(
                actor=actor,
                action="order.fulfillment_advanced",
                object_type="orders.Order",
                object_id=str(order.id),
                summary=f"Order fulfillment advanced from {previous_status} to {order.status}.",
                metadata={
                    "publicId": str(order.public_id),
                    "fromStatus": previous_status,
                    "toStatus": order.status,
                },
            )
        return order


def set_inventory_as_staff(
    actor: User,
    *,
    variant_id: UUID,
    on_hand: int,
    is_active: bool,
) -> VariantInventory:
    require_staff_permission(actor, "commerce.change_variantinventory")
    with transaction.atomic():
        inventory = VariantInventory.objects.select_for_update().get(variant_id=variant_id)
        before = {"onHand": inventory.on_hand, "isActive": inventory.is_active}
        inventory = set_on_hand(variant_id, quantity=on_hand)
        if inventory.is_active != is_active:
            inventory.is_active = is_active
            inventory.save(update_fields=("is_active", "updated_at"))
        after = {"onHand": inventory.on_hand, "isActive": inventory.is_active}
        if after != before:
            append_audit_event(
                actor=actor,
                action="inventory.updated",
                object_type="commerce.VariantInventory",
                object_id=str(inventory.id),
                summary="Variant inventory updated through the staff service boundary.",
                metadata={"variantId": str(variant_id), "before": before, "after": after},
            )
        return inventory


def set_price_as_staff(
    actor: User,
    *,
    variant_id: UUID,
    amount_toman: Decimal,
    compare_at_toman: Decimal | None,
    is_active: bool,
) -> VariantPrice:
    require_staff_permission(actor, "commerce.change_variantprice")
    if amount_toman < 0:
        raise ValueError("Price cannot be negative.")
    if compare_at_toman is not None and compare_at_toman <= amount_toman:
        raise ValueError("Compare-at price must be greater than the active price.")

    with transaction.atomic():
        ProductVariant.objects.select_for_update().get(pk=variant_id)
        existing = VariantPrice.objects.select_for_update().filter(variant_id=variant_id).first()
        before: dict[str, Any] | None = None
        if existing is not None:
            before = {
                "amountToman": int(existing.amount_toman),
                "compareAtToman": (
                    int(existing.compare_at_toman)
                    if existing.compare_at_toman is not None
                    else None
                ),
                "isActive": existing.is_active,
            }
            price = existing
            price.amount_toman = amount_toman
            price.compare_at_toman = compare_at_toman
            price.is_active = is_active
            price.save(
                update_fields=("amount_toman", "compare_at_toman", "is_active", "updated_at")
            )
        else:
            price = VariantPrice.objects.create(
                variant_id=variant_id,
                amount_toman=amount_toman,
                compare_at_toman=compare_at_toman,
                is_active=is_active,
            )
        after = {
            "amountToman": int(price.amount_toman),
            "compareAtToman": int(price.compare_at_toman)
            if price.compare_at_toman is not None
            else None,
            "isActive": price.is_active,
        }
        if before != after:
            append_audit_event(
                actor=actor,
                action="price.updated",
                object_type="commerce.VariantPrice",
                object_id=str(price.id),
                summary="Variant price updated through the staff service boundary.",
                metadata={"variantId": str(variant_id), "before": before, "after": after},
            )
        return price
