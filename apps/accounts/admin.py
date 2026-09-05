from typing import Any

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.db import transaction
from django.http import HttpRequest

from apps.operations.audit import append_audit_event

from .models import Address, User


@admin.register(User)
class VisioUserAdmin(UserAdmin):
    def get_readonly_fields(
        self,
        request: HttpRequest,
        obj: User | None = None,
    ) -> tuple[str, ...]:
        fields = tuple(super().get_readonly_fields(request, obj))
        if request.user.is_superuser:
            return fields
        return fields + ("is_staff", "is_superuser", "groups", "user_permissions")

    def has_delete_permission(self, request: HttpRequest, obj: User | None = None) -> bool:
        return False

    def save_model(
        self,
        request: HttpRequest,
        obj: User,
        form: Any,
        change: bool,
    ) -> None:
        before = None
        if change and obj.pk:
            existing = User.objects.get(pk=obj.pk)
            before = {
                "email": existing.email,
                "isActive": existing.is_active,
                "isStaff": existing.is_staff,
                "isSuperuser": existing.is_superuser,
            }
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            append_audit_event(
                actor=request.user,
                action="account.updated" if change else "account.created",
                object_type="accounts.User",
                object_id=str(obj.pk),
                summary="Staff account mutation through Django Admin.",
                metadata={
                    "before": before,
                    "after": {
                        "email": obj.email,
                        "isActive": obj.is_active,
                        "isStaff": obj.is_staff,
                        "isSuperuser": obj.is_superuser,
                    },
                },
            )


@admin.register(Address)
class AddressAdmin(admin.ModelAdmin):
    list_display = ("user", "label", "province", "city", "is_default", "updated_at")
    search_fields = ("user__email", "recipient_name", "recipient_phone", "postal_code")
    list_filter = ("country_code", "province", "city", "is_default")
    readonly_fields = (
        "id",
        "user",
        "label",
        "recipient_name",
        "recipient_phone",
        "country_code",
        "province",
        "city",
        "postal_code",
        "address_line1",
        "address_line2",
        "is_default",
        "created_at",
        "updated_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Address | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Address | None = None) -> bool:
        return False
