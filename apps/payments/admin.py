from django.contrib import admin
from django.http import HttpRequest

from .models import PaymentAttempt, PaymentReconciliation


@admin.register(PaymentAttempt)
class PaymentAttemptAdmin(admin.ModelAdmin[PaymentAttempt]):
    list_display = (
        "created_at",
        "order",
        "provider",
        "status",
        "amount_toman",
        "provider_ref_id",
        "verified_at",
    )
    list_filter = ("provider", "status", "created_at")
    search_fields = ("order__public_id", "provider_authority", "provider_ref_id")
    ordering = ("-created_at",)
    readonly_fields = (
        "id",
        "order",
        "idempotency_key",
        "provider",
        "status",
        "amount_toman",
        "amount_rial",
        "currency_code",
        "display_unit",
        "provider_authority",
        "provider_redirect_url",
        "provider_ref_id",
        "provider_code",
        "provider_message",
        "masked_card",
        "card_hash",
        "last_callback_status",
        "request_count",
        "callback_count",
        "verify_count",
        "verified_at",
        "status_changed_at",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: PaymentAttempt | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: PaymentAttempt | None = None) -> bool:
        return False


@admin.register(PaymentReconciliation)
class PaymentReconciliationAdmin(admin.ModelAdmin[PaymentReconciliation]):
    list_display = ("checked_at", "attempt", "status", "provider_code", "provider_ref_id")
    list_filter = ("status", "checked_at")
    search_fields = ("attempt__order__public_id", "provider_ref_id", "detail")
    ordering = ("-checked_at",)
    readonly_fields = (
        "id",
        "attempt",
        "status",
        "provider_code",
        "provider_ref_id",
        "provider_payload_digest",
        "detail",
        "checked_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self,
        request: HttpRequest,
        obj: PaymentReconciliation | None = None,
    ) -> bool:
        return False

    def has_delete_permission(
        self,
        request: HttpRequest,
        obj: PaymentReconciliation | None = None,
    ) -> bool:
        return False
