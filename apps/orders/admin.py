from django.contrib import admin, messages
from django.core.exceptions import ValidationError
from django.db.models import QuerySet
from django.http import HttpRequest

from apps.operations.staff_services import advance_order_as_staff

from .models import Order, OrderLine
from .services import OrderError


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin[Order]):
    list_display = ("public_id", "user", "status", "payable_toman", "status_changed_at", "created_at")
    list_filter = ("status", "created_at")
    search_fields = ("public_id", "user__email")
    ordering = ("-created_at",)
    readonly_fields = (
        "id",
        "public_id",
        "user",
        "checkout",
        "idempotency_key",
        "status",
        "status_changed_at",
        "customer_snapshot",
        "address_snapshot",
        "shipping_snapshot",
        "subtotal_toman",
        "discount_toman",
        "shipping_toman",
        "tax_toman",
        "payable_toman",
        "tax_rate_bps",
        "created_at",
        "updated_at",
    )
    actions = ("mark_processing", "mark_shipped", "mark_delivered")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Order | None = None) -> bool:
        return False

    def save_model(self, request: HttpRequest, obj: Order, form: object, change: bool) -> None:
        raise ValidationError("Orders cannot be edited directly; use the controlled fulfillment actions.")

    def _advance_selected(
        self,
        request: HttpRequest,
        queryset: QuerySet[Order],
        *,
        target_status: str,
    ) -> None:
        changed = 0
        failed = 0
        for order in queryset.order_by("created_at", "id"):
            try:
                result = advance_order_as_staff(
                    request.user,
                    order_id=order.id,
                    target_status=target_status,
                )
            except OrderError as exc:
                failed += 1
                self.message_user(request, f"{order.public_id}: {exc}", level=messages.WARNING)
                continue
            if result.status == target_status:
                changed += 1
        self.message_user(
            request,
            f"Fulfillment action result: transitioned={changed}, failed={failed}.",
            level=messages.INFO if failed == 0 else messages.WARNING,
        )

    @admin.action(description="Advance selected orders to processing")
    def mark_processing(self, request: HttpRequest, queryset: QuerySet[Order]) -> None:
        self._advance_selected(request, queryset, target_status=Order.Status.PROCESSING)

    @admin.action(description="Advance selected orders to shipped")
    def mark_shipped(self, request: HttpRequest, queryset: QuerySet[Order]) -> None:
        self._advance_selected(request, queryset, target_status=Order.Status.SHIPPED)

    @admin.action(description="Advance selected orders to delivered")
    def mark_delivered(self, request: HttpRequest, queryset: QuerySet[Order]) -> None:
        self._advance_selected(request, queryset, target_status=Order.Status.DELIVERED)


@admin.register(OrderLine)
class OrderLineAdmin(admin.ModelAdmin[OrderLine]):
    list_display = ("order", "source_variant_sku", "quantity", "unit_price_toman", "line_total_toman")
    search_fields = ("order__public_id", "source_variant_sku", "source_product_name")
    readonly_fields = (
        "id",
        "order",
        "reservation",
        "source_product_id",
        "source_product_slug",
        "source_product_name",
        "source_variant_id",
        "source_variant_sku",
        "option_snapshot",
        "quantity",
        "unit_price_toman",
        "line_total_toman",
        "created_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: OrderLine | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: OrderLine | None = None) -> bool:
        return False
