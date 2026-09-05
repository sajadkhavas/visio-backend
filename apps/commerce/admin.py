from typing import Any
from uuid import UUID

from django.contrib import admin
from django.http import HttpRequest

from apps.operations.staff_services import set_inventory_as_staff, set_price_as_staff

from .models import InventoryReservation, VariantInventory, VariantPrice


@admin.register(VariantPrice)
class VariantPriceAdmin(admin.ModelAdmin):
    list_display = ("variant", "amount_toman", "compare_at_toman", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("variant__sku", "variant__product__name")

    def has_delete_permission(self, request: HttpRequest, obj: VariantPrice | None = None) -> bool:
        return False

    def save_model(
        self,
        request: HttpRequest,
        obj: VariantPrice,
        form: Any,
        change: bool,
    ) -> None:
        price = set_price_as_staff(
            request.user,
            variant_id=UUID(str(obj.variant_id)),
            amount_toman=obj.amount_toman,
            compare_at_toman=obj.compare_at_toman,
            is_active=obj.is_active,
        )
        obj.pk = price.pk
        obj.id = price.id
        obj.created_at = price.created_at
        obj.updated_at = price.updated_at


@admin.register(VariantInventory)
class VariantInventoryAdmin(admin.ModelAdmin):
    list_display = ("variant", "on_hand", "is_active", "updated_at")
    list_filter = ("is_active",)
    search_fields = ("variant__sku", "variant__product__name")

    def has_delete_permission(
        self,
        request: HttpRequest,
        obj: VariantInventory | None = None,
    ) -> bool:
        return False

    def save_model(
        self,
        request: HttpRequest,
        obj: VariantInventory,
        form: Any,
        change: bool,
    ) -> None:
        inventory = set_inventory_as_staff(
            request.user,
            variant_id=UUID(str(obj.variant_id)),
            on_hand=obj.on_hand,
            is_active=obj.is_active,
        )
        obj.pk = inventory.pk
        obj.id = inventory.id
        obj.created_at = inventory.created_at
        obj.updated_at = inventory.updated_at


@admin.register(InventoryReservation)
class InventoryReservationAdmin(admin.ModelAdmin):
    list_display = ("inventory", "quantity", "status", "expires_at", "created_at")
    list_filter = ("status", "expires_at")
    search_fields = ("inventory__variant__sku", "inventory__variant__product__name")
    readonly_fields = (
        "id",
        "inventory",
        "quantity",
        "status",
        "expires_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self,
        request: HttpRequest,
        obj: InventoryReservation | None = None,
    ) -> bool:
        return False

    def has_delete_permission(
        self,
        request: HttpRequest,
        obj: InventoryReservation | None = None,
    ) -> bool:
        return False
