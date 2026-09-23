from typing import Any

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest

from apps.accounts.models import User

from .models import CheckoutTaxPolicy, ShippingMethod, ShippingZone
from .staff_services import (
    save_shipping_method_as_staff,
    save_shipping_zone_as_staff,
    save_tax_policy_as_staff,
)


def _staff_actor(request: HttpRequest) -> User:
    actor = request.user
    if not isinstance(actor, User):
        raise PermissionDenied("Authenticated VISIO staff user required.")
    return actor


class NoDeleteConfigurationAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request: HttpRequest, obj: object | None = None) -> bool:
        return False


@admin.register(ShippingZone)
class ShippingZoneAdmin(NoDeleteConfigurationAdmin):
    list_display = ("code", "name", "country_code", "province", "city", "is_active")
    list_filter = ("country_code", "is_active")
    search_fields = ("code", "name", "province", "city")
    ordering = ("country_code", "province", "city", "code")

    def save_model(
        self,
        request: HttpRequest,
        obj: ShippingZone,
        form: Any,
        change: bool,
    ) -> None:
        del form
        save_shipping_zone_as_staff(_staff_actor(request), obj, change=change)


@admin.register(ShippingMethod)
class ShippingMethodAdmin(NoDeleteConfigurationAdmin):
    list_display = (
        "code",
        "name",
        "zone",
        "flat_rate_toman",
        "free_over_toman",
        "is_active",
    )
    list_filter = ("is_active", "zone__country_code")
    search_fields = ("code", "name", "zone__code", "zone__name")
    ordering = ("sort_order", "code", "id")

    def save_model(
        self,
        request: HttpRequest,
        obj: ShippingMethod,
        form: Any,
        change: bool,
    ) -> None:
        del form
        save_shipping_method_as_staff(_staff_actor(request), obj, change=change)


@admin.register(CheckoutTaxPolicy)
class CheckoutTaxPolicyAdmin(NoDeleteConfigurationAdmin):
    list_display = ("country_code", "rate_bps", "applies_to_shipping", "is_active", "updated_at")
    list_filter = ("is_active", "applies_to_shipping")
    search_fields = ("country_code",)
    ordering = ("country_code", "id")

    def save_model(
        self,
        request: HttpRequest,
        obj: CheckoutTaxPolicy,
        form: Any,
        change: bool,
    ) -> None:
        del form
        save_tax_policy_as_staff(_staff_actor(request), obj, change=change)
