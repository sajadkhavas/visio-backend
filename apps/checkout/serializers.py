from __future__ import annotations

from typing import Any

from rest_framework import serializers

from apps.commerce.projections import CURRENCY_CODE, DISPLAY_UNIT

from .models import CheckoutSession
from .services import ShippingQuote


class ShippingOptionsQuerySerializer(serializers.Serializer):
    addressId = serializers.IntegerField(min_value=1)


class CheckoutCreateSerializer(serializers.Serializer):
    addressId = serializers.IntegerField(min_value=1)
    shippingMethodCode = serializers.CharField(max_length=64, trim_whitespace=True)
    idempotencyKey = serializers.UUIDField()


class CheckoutFinalizeSerializer(serializers.Serializer):
    idempotencyKey = serializers.UUIDField()


def _money(amount_toman: int, *, revision: str | None = None) -> dict[str, Any]:
    return {
        "amount": amount_toman,
        "currency": CURRENCY_CODE,
        "displayUnit": DISPLAY_UNIT,
        "authority": "server-validated",
        "revision": revision,
    }


def shipping_quote_payload(quote: ShippingQuote) -> dict[str, Any]:
    method = quote.method
    revision = method.updated_at.isoformat()
    return {
        "method": {
            "id": str(method.pk),
            "code": method.code,
            "name": method.name,
            "zoneCode": method.zone.code,
            "deliveryMinDays": method.delivery_min_days,
            "deliveryMaxDays": method.delivery_max_days,
        },
        "totals": {
            "subtotal": _money(quote.subtotal_toman, revision=revision),
            "discount": _money(quote.discount_toman, revision=revision),
            "shipping": _money(quote.shipping_toman, revision=revision),
            "tax": _money(quote.tax_toman, revision=revision),
            "payable": _money(quote.payable_toman, revision=revision),
            "taxRateBps": quote.tax_rate_bps,
            "provisional": True,
        },
    }


def checkout_payload(session: CheckoutSession) -> dict[str, Any]:
    lines = list(
        session.lines.select_related("variant", "variant__product", "reservation")
        .order_by("variant_id", "id")
        .all()
    )
    revision = session.updated_at.isoformat()
    payload: dict[str, Any] = {
        "id": str(session.pk),
        "status": session.status,
        "cartId": str(session.cart_id),
        "cartRevision": session.cart_revision,
        "address": session.address_snapshot,
        "shipping": session.shipping_snapshot,
        "lines": [
            {
                "productId": str(line.variant.product_id),
                "variantId": str(line.variant_id),
                "quantity": line.quantity,
                "unitPrice": _money(int(line.unit_price_toman), revision=revision),
                "lineTotal": _money(int(line.line_total_toman), revision=revision),
                "reservation": {
                    "id": str(line.reservation_id),
                    "status": line.reservation.status,
                    "expiresAt": line.reservation.expires_at.isoformat(),
                },
            }
            for line in lines
        ],
        "totals": {
            "subtotal": _money(int(session.subtotal_toman), revision=revision),
            "discount": _money(int(session.discount_toman), revision=revision),
            "shipping": _money(int(session.shipping_toman), revision=revision),
            "tax": _money(int(session.tax_toman), revision=revision),
            "payable": _money(int(session.payable_toman), revision=revision),
            "taxRateBps": session.tax_rate_bps,
            "provisional": session.status != CheckoutSession.Status.READY,
            "validatedAt": session.finalized_at.isoformat() if session.finalized_at else None,
        },
        "expiresAt": session.expires_at.isoformat(),
        "createdAt": session.created_at.isoformat(),
        "updatedAt": session.updated_at.isoformat(),
    }
    if session.status == CheckoutSession.Status.READY:
        payload["handoff"] = {
            "checkoutId": str(session.pk),
            "cartRevision": session.cart_revision,
            "validatedAt": session.finalized_at.isoformat() if session.finalized_at else None,
            "expiresAt": session.expires_at.isoformat(),
        }
    else:
        payload["handoff"] = None
    return payload
