from __future__ import annotations

from django.db import transaction

from apps.accounts.models import User
from apps.operations.audit import append_audit_event
from apps.operations.permissions import require_staff_permission

from .models import CheckoutTaxPolicy, ShippingMethod, ShippingZone


def _permission(model_name: str, *, change: bool) -> str:
    action = "change" if change else "add"
    return f"checkout.{action}_{model_name}"


def save_shipping_zone_as_staff(
    actor: User,
    zone: ShippingZone,
    *,
    change: bool,
) -> ShippingZone:
    require_staff_permission(actor, _permission("shippingzone", change=change))

    with transaction.atomic():
        zone.full_clean()
        zone.save()
        append_audit_event(
            actor=actor,
            action="shipping.zone.updated" if change else "shipping.zone.created",
            object_type="checkout.ShippingZone",
            object_id=str(zone.pk),
            summary="Shipping zone changed through the staff service boundary.",
            metadata={
                "code": zone.code,
                "countryCode": zone.country_code,
                "province": zone.province,
                "city": zone.city,
                "isActive": zone.is_active,
            },
        )
    return zone


def save_shipping_method_as_staff(
    actor: User,
    method: ShippingMethod,
    *,
    change: bool,
) -> ShippingMethod:
    require_staff_permission(actor, _permission("shippingmethod", change=change))

    with transaction.atomic():
        method.full_clean()
        method.save()
        append_audit_event(
            actor=actor,
            action="shipping.method.updated" if change else "shipping.method.created",
            object_type="checkout.ShippingMethod",
            object_id=str(method.pk),
            summary="Shipping method changed through the staff service boundary.",
            metadata={
                "zoneId": str(method.zone_id),
                "code": method.code,
                "flatRateToman": int(method.flat_rate_toman),
                "freeOverToman": (
                    int(method.free_over_toman) if method.free_over_toman is not None else None
                ),
                "deliveryMinDays": method.delivery_min_days,
                "deliveryMaxDays": method.delivery_max_days,
                "isActive": method.is_active,
            },
        )
    return method


def save_tax_policy_as_staff(
    actor: User,
    policy: CheckoutTaxPolicy,
    *,
    change: bool,
) -> CheckoutTaxPolicy:
    require_staff_permission(actor, _permission("checkouttaxpolicy", change=change))

    with transaction.atomic():
        policy.full_clean()
        policy.save()
        append_audit_event(
            actor=actor,
            action="tax.policy.updated" if change else "tax.policy.created",
            object_type="checkout.CheckoutTaxPolicy",
            object_id=str(policy.pk),
            summary="Checkout tax policy changed through the staff service boundary.",
            metadata={
                "countryCode": policy.country_code,
                "rateBps": policy.rate_bps,
                "appliesToShipping": policy.applies_to_shipping,
                "isActive": policy.is_active,
            },
        )
    return policy
