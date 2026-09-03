from __future__ import annotations

from datetime import datetime
from typing import Any

from django.core.exceptions import ObjectDoesNotExist

from apps.catalog.models import ProductVariant

from .models import InventoryReservation, VariantInventory, VariantPrice

CURRENCY_CODE = "IRR"
DISPLAY_UNIT = "تومان"


def _price_record(variant: ProductVariant) -> VariantPrice | None:
    try:
        price = variant.price_record
    except ObjectDoesNotExist:
        return None
    return price if price.is_active else None


def _inventory_record(variant: ProductVariant) -> VariantInventory | None:
    try:
        inventory = variant.inventory_record
    except ObjectDoesNotExist:
        return None
    return inventory if inventory.is_active else None


def money_payload(amount_toman: int) -> dict[str, Any]:
    return {
        "amount": amount_toman,
        "currency": CURRENCY_CODE,
        "displayUnit": DISPLAY_UNIT,
    }


def variant_price_payload(variant: ProductVariant) -> dict[str, Any]:
    price = _price_record(variant)
    if price is None:
        return {
            "current": None,
            "compareAt": None,
            "authoritative": False,
            "source": "backend",
            "updatedAt": None,
        }

    compare_at = None
    if price.compare_at_toman is not None:
        compare_at = money_payload(int(price.compare_at_toman))

    return {
        "current": money_payload(int(price.amount_toman)),
        "compareAt": compare_at,
        "authoritative": True,
        "source": "backend",
        "updatedAt": price.updated_at.isoformat(),
    }


def active_reserved_quantity(inventory: VariantInventory, *, at: datetime) -> int:
    reservations = getattr(inventory, "active_reservations", None)
    if reservations is None:
        reservations = inventory.reservations.filter(
            status=InventoryReservation.Status.ACTIVE,
            expires_at__gt=at,
        )
    return sum(
        reservation.quantity
        for reservation in reservations
        if reservation.status == InventoryReservation.Status.ACTIVE and reservation.expires_at > at
    )


def variant_availability_payload(
    variant: ProductVariant,
    *,
    at: datetime,
) -> dict[str, Any]:
    inventory = _inventory_record(variant)
    if inventory is None or not variant.is_active:
        return {
            "status": "unknown",
            "authoritative": False,
            "maxQuantity": None,
            "updatedAt": None,
        }

    reserved = active_reserved_quantity(inventory, at=at)
    available = inventory.on_hand - reserved
    if available < 0:
        return {
            "status": "unknown",
            "authoritative": False,
            "maxQuantity": None,
            "updatedAt": inventory.updated_at.isoformat(),
        }

    return {
        "status": "in-stock" if available > 0 else "out-of-stock",
        "authoritative": True,
        "maxQuantity": available,
        "updatedAt": inventory.updated_at.isoformat(),
    }


def variant_is_on_sale(variant: ProductVariant) -> bool:
    price = _price_record(variant)
    return bool(price is not None and price.compare_at_toman is not None)
