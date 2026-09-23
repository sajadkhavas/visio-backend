from decimal import Decimal

import pytest
from apps.accounts.models import User
from apps.checkout.models import CheckoutTaxPolicy, ShippingMethod, ShippingZone
from apps.checkout.staff_services import (
    save_shipping_method_as_staff,
    save_shipping_zone_as_staff,
    save_tax_policy_as_staff,
)
from apps.operations.models import AuditEvent
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError

pytestmark = pytest.mark.django_db(transaction=True)


def permission(app_label: str, codename: str) -> Permission:
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def staff_user(email: str, *permissions: Permission) -> User:
    user = User.objects.create_user(
        username=email,
        email=email,
        password="Correct-Horse-Battery-77",
        is_staff=True,
    )
    user.user_permissions.add(*permissions)
    return user


def test_shipping_zone_staff_service_enforces_permission_and_audits() -> None:
    denied = staff_user("shipping-denied@example.com")
    with pytest.raises(PermissionDenied):
        save_shipping_zone_as_staff(
            denied,
            ShippingZone(
                code="denied-zone",
                name="Denied zone",
                country_code="IR",
            ),
            change=False,
        )
    assert not ShippingZone.objects.filter(code="denied-zone").exists()

    actor = staff_user(
        "shipping-zone@example.com",
        permission("checkout", "add_shippingzone"),
    )
    zone = save_shipping_zone_as_staff(
        actor,
        ShippingZone(
            code="tehran-safe",
            name="Tehran safe",
            country_code="IR",
            province="Tehran",
            city="Tehran",
        ),
        change=False,
    )

    event = AuditEvent.objects.get(actor=actor, action="shipping.zone.created")
    assert zone.pk is not None
    assert event.object_id == str(zone.pk)
    assert event.metadata["code"] == "tehran-safe"


def test_shipping_method_staff_service_rejects_invalid_delivery_range() -> None:
    zone = ShippingZone.objects.create(
        code="method-zone",
        name="Method zone",
        country_code="IR",
    )
    actor = staff_user(
        "shipping-method@example.com",
        permission("checkout", "add_shippingmethod"),
    )

    with pytest.raises(ValidationError):
        save_shipping_method_as_staff(
            actor,
            ShippingMethod(
                zone=zone,
                code="invalid-range",
                name="Invalid range",
                flat_rate_toman=Decimal(50_000),
                delivery_min_days=4,
                delivery_max_days=2,
            ),
            change=False,
        )

    assert not ShippingMethod.objects.filter(code="invalid-range").exists()
    assert not AuditEvent.objects.filter(actor=actor, action="shipping.method.created").exists()


def test_shipping_method_staff_service_saves_and_audits_valid_configuration() -> None:
    zone = ShippingZone.objects.create(
        code="valid-method-zone",
        name="Valid method zone",
        country_code="IR",
    )
    actor = staff_user(
        "shipping-method-valid@example.com",
        permission("checkout", "add_shippingmethod"),
    )

    method = save_shipping_method_as_staff(
        actor,
        ShippingMethod(
            zone=zone,
            code="standard-safe",
            name="Standard safe",
            flat_rate_toman=Decimal(60_000),
            free_over_toman=Decimal(1_000_000),
            delivery_min_days=1,
            delivery_max_days=3,
        ),
        change=False,
    )

    event = AuditEvent.objects.get(actor=actor, action="shipping.method.created")
    assert method.pk is not None
    assert event.metadata["flatRateToman"] == 60_000
    assert event.metadata["freeOverToman"] == 1_000_000


def test_tax_policy_staff_service_enforces_single_active_country_policy() -> None:
    CheckoutTaxPolicy.objects.create(
        country_code="IR",
        rate_bps=900,
        is_active=True,
    )
    actor = staff_user(
        "tax-policy@example.com",
        permission("checkout", "add_checkouttaxpolicy"),
    )

    with pytest.raises(ValidationError):
        save_tax_policy_as_staff(
            actor,
            CheckoutTaxPolicy(
                country_code="IR",
                rate_bps=1_000,
                applies_to_shipping=False,
                is_active=True,
            ),
            change=False,
        )

    assert CheckoutTaxPolicy.objects.filter(country_code="IR", is_active=True).count() == 1
    assert not AuditEvent.objects.filter(actor=actor, action="tax.policy.created").exists()


def test_tax_policy_staff_service_audits_valid_policy() -> None:
    actor = staff_user(
        "tax-policy-valid@example.com",
        permission("checkout", "add_checkouttaxpolicy"),
    )

    policy = save_tax_policy_as_staff(
        actor,
        CheckoutTaxPolicy(
            country_code="IR",
            rate_bps=1_000,
            applies_to_shipping=True,
            is_active=True,
        ),
        change=False,
    )

    event = AuditEvent.objects.get(actor=actor, action="tax.policy.created")
    assert policy.pk is not None
    assert event.metadata == {
        "countryCode": "IR",
        "rateBps": 1_000,
        "appliesToShipping": True,
        "isActive": True,
    }
