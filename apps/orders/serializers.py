from __future__ import annotations

from typing import Any

from rest_framework import serializers

from .models import Order, OrderLine


class OrderCreateSerializer(serializers.Serializer):
    checkoutId = serializers.UUIDField()
    idempotencyKey = serializers.UUIDField()


def _money(amount: int, order: Order) -> dict[str, Any]:
    return {
        "amount": amount,
        "currency": order.currency_code,
        "displayUnit": order.display_unit,
    }


def order_line_payload(line: OrderLine) -> dict[str, Any]:
    return {
        "product": {
            "id": str(line.source_product_id),
            "slug": line.source_product_slug,
            "name": line.source_product_name,
        },
        "variant": {
            "id": str(line.source_variant_id),
            "sku": line.source_variant_sku,
            "options": line.option_snapshot,
        },
        "quantity": line.quantity,
        "unitPrice": {
            "amount": int(line.unit_price_toman),
            "currency": "IRR",
            "displayUnit": "تومان",
        },
        "lineTotal": {
            "amount": int(line.line_total_toman),
            "currency": "IRR",
            "displayUnit": "تومان",
        },
    }


def order_payload(order: Order, *, include_lines: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": str(order.public_id),
        "status": order.status,
        "customer": order.customer_snapshot,
        "address": order.address_snapshot,
        "shipping": order.shipping_snapshot,
        "totals": {
            "subtotal": _money(int(order.subtotal_toman), order),
            "discount": _money(int(order.discount_toman), order),
            "shipping": _money(int(order.shipping_toman), order),
            "tax": _money(int(order.tax_toman), order),
            "payable": _money(int(order.payable_toman), order),
            "taxRateBps": order.tax_rate_bps,
        },
        "statusChangedAt": order.status_changed_at.isoformat(),
        "createdAt": order.created_at.isoformat(),
        "updatedAt": order.updated_at.isoformat(),
    }
    lines = list(order.lines.all())
    payload["lineCount"] = len(lines)
    if include_lines:
        payload["lines"] = [order_line_payload(line) for line in lines]
    return payload
