from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import quote
from uuid import UUID

from django.utils import timezone
from rest_framework import serializers

from apps.catalog.models import Product, ProductVariant
from apps.commerce.projections import variant_availability_payload, variant_price_payload

from .models import CART_MAX_QUANTITY, Cart, WishlistItem
from .services import MAX_IMPORT_LINES

CART_PERSISTENCE_VERSION = 2
_URI_COMPONENT_SAFE = "-_.!~*'()"


class ClientPriceSnapshotSerializer(serializers.Serializer):
    amount = serializers.IntegerField(min_value=0)
    currency = serializers.CharField(allow_null=True, required=False)
    displayUnit = serializers.CharField(allow_null=True, required=False)
    authority = serializers.ChoiceField(choices=("client-snapshot", "server-validated"))
    capturedAt = serializers.DateTimeField(allow_null=True, required=False)
    revision = serializers.CharField(allow_null=True, required=False)


class CartIdentityInputSerializer(serializers.Serializer):
    variantId = serializers.UUIDField()


class CartMutationSerializer(serializers.Serializer):
    variantId = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1, max_value=CART_MAX_QUANTITY)
    priceSnapshot = ClientPriceSnapshotSerializer(required=False, allow_null=True)


class CartQuantitySerializer(serializers.Serializer):
    quantity = serializers.IntegerField(min_value=1, max_value=CART_MAX_QUANTITY)


class BrowserCartItemSerializer(serializers.Serializer):
    identity = CartIdentityInputSerializer()
    quantity = serializers.IntegerField(min_value=1, max_value=CART_MAX_QUANTITY)
    priceSnapshot = ClientPriceSnapshotSerializer(required=False, allow_null=True)


class BrowserCartImportSerializer(serializers.Serializer):
    items = BrowserCartItemSerializer(many=True, max_length=MAX_IMPORT_LINES)


class CartValidateSerializer(serializers.Serializer):
    items = BrowserCartItemSerializer(many=True, max_length=MAX_IMPORT_LINES, required=False)


class WishlistResponseSerializer(serializers.Serializer):
    productIds = serializers.ListField(child=serializers.UUIDField())


def _normalized_options(variant: ProductVariant) -> dict[str, str]:
    selections = (
        variant.option_selections.select_related("option", "value")
        .order_by("option__key", "id")
        .all()
    )
    return {selection.option.key: selection.value.value for selection in selections}


def _identity_payload(variant: ProductVariant) -> dict[str, Any]:
    options = _normalized_options(variant)
    option_part = "&".join(
        f"{quote(name, safe=_URI_COMPONENT_SAFE)}={quote(value, safe=_URI_COMPONENT_SAFE)}"
        for name, value in options.items()
    )
    product_id = str(variant.product_id)
    variant_id = str(variant.id)
    key = "::".join((product_id, variant_id, option_part or "default"))
    return {
        "productId": product_id,
        "variantId": variant_id,
        "options": options,
        "key": key,
    }


def _server_price_snapshot(variant: ProductVariant) -> dict[str, Any] | None:
    contract = variant_price_payload(variant)
    current = contract["current"]
    if not contract["authoritative"] or not isinstance(current, dict):
        return None
    revision = contract["updatedAt"]
    return {
        "amount": int(current["amount"]),
        "currency": current["currency"],
        "displayUnit": current["displayUnit"],
        "authority": "server-validated",
        "capturedAt": revision,
        "revision": revision,
    }


def _client_snapshot_payload(snapshot: dict[str, Any]) -> dict[str, Any]:
    captured_at = snapshot.get("capturedAt")
    if isinstance(captured_at, datetime):
        captured_at = captured_at.isoformat()
    return {
        "amount": int(snapshot["amount"]),
        "currency": snapshot.get("currency"),
        "displayUnit": snapshot.get("displayUnit"),
        "authority": str(snapshot["authority"]),
        "capturedAt": captured_at,
        "revision": snapshot.get("revision"),
    }


def _price_changed(previous: dict[str, Any], current: dict[str, Any]) -> bool:
    return any(
        previous.get(field) != current.get(field) for field in ("amount", "currency", "displayUnit")
    )


def cart_payload(
    cart: Cart,
    *,
    snapshots: dict[UUID, dict[str, Any]] | None = None,
    adjusted: dict[UUID, int] | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    snapshot_map = snapshots or {}
    adjusted_map = adjusted or {}
    now = timezone.now()
    items: list[dict[str, Any]] = []
    issues: list[dict[str, Any]] = []
    subtotal = 0
    subtotal_authoritative = True

    lines = (
        cart.lines.select_related("variant", "variant__product").order_by("added_at", "id").all()
    )
    for line in lines:
        variant = line.variant
        identity = _identity_payload(variant)
        key = str(identity["key"])
        current_price = _server_price_snapshot(variant)

        if current_price is None:
            subtotal_authoritative = False
        else:
            subtotal += int(current_price["amount"]) * line.quantity

        if not variant.is_active or variant.product.status != Product.Status.PUBLISHED:
            availability: dict[str, Any] = {
                "status": "variant-unavailable",
                "checkedAt": now.isoformat(),
            }
            issues.append({"type": "variant-unavailable", "key": key})
        else:
            authority = variant_availability_payload(variant, at=now)
            if not authority["authoritative"]:
                availability = {"status": "unknown", "checkedAt": now.isoformat()}
            elif authority["status"] == "out-of-stock":
                availability = {"status": "sold-out", "checkedAt": now.isoformat()}
                issues.append({"type": "sold-out", "key": key})
            else:
                availability = {"status": "available"}

        allowed = adjusted_map.get(variant.id)
        if allowed is not None:
            issues.append({"type": "quantity-adjusted", "key": key, "allowed": allowed})

        mismatch = None
        supplied = snapshot_map.get(variant.id)
        if supplied is not None and current_price is not None:
            previous = _client_snapshot_payload(supplied)
            if _price_changed(previous, current_price):
                mismatch = {
                    "status": "changed",
                    "previous": previous,
                    "current": current_price,
                    "acknowledged": False,
                }
                issues.append({"type": "price-changed", "key": key, "current": current_price})

        items.append(
            {
                "identity": identity,
                "quantity": line.quantity,
                "quantityConstraints": {"min": 1, "max": CART_MAX_QUANTITY, "step": 1},
                "availability": availability,
                "priceSnapshot": current_price,
                "priceMismatch": mismatch,
                "addedAt": line.added_at.isoformat(),
                "updatedAt": line.updated_at.isoformat(),
            }
        )

    subtotal_snapshot = None
    if subtotal_authoritative:
        subtotal_snapshot = {
            "amount": subtotal,
            "currency": "IRR",
            "displayUnit": "تومان",
            "authority": "server-validated",
            "capturedAt": now.isoformat(),
            "revision": str(cart.revision),
        }

    payload = {
        "id": str(cart.id),
        "version": CART_PERSISTENCE_VERSION,
        "serverRevision": cart.revision,
        "items": items,
        "totals": {
            "itemCount": sum(int(item["quantity"]) for item in items),
            "subtotal": subtotal_snapshot,
            "discount": None,
            "shipping": None,
            "tax": None,
            "payable": None,
            "provisional": True,
            "validatedAt": now.isoformat(),
        },
        "status": "ready",
        "error": None,
        "updatedAt": cart.updated_at.isoformat(),
    }
    return payload, issues


def wishlist_payload(user_id: int) -> dict[str, list[str]]:
    product_ids = WishlistItem.objects.filter(user_id=user_id).values_list(
        "product_id",
        flat=True,
    )
    return {"productIds": [str(product_id) for product_id in product_ids]}
