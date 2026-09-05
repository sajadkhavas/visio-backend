from typing import Any

from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpRequest

from apps.operations.audit import append_audit_event

from .models import Address, User


def _require_staff_user(request: HttpRequest) -> User:
    actor = request.user
    if not isinstance(actor, User) or not actor.is_staff:
        raise PermissionDenied("Authenticated staff user required for admin mutation.")
    return actor


if admin.site.is_registered(Group):
    admin.site.unregister(Group)


@admin.register(Group)
class ReadOnlyRoleDefinitionAdmin(GroupAdmin):
    """Role definitions are code-owned by the deterministic B09 role matrix."""

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Group | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Group | None = None) -> bool:
        return False


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
        actor = _require_staff_user(request)
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
                actor=actor,
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

    def save_related(
        self,
        request: HttpRequest,
        form: Any,
        formsets: Any,
        change: bool,
    ) -> None:
        actor = _require_staff_user(request)
        with transaction.atomic():
            super().save_related(request, form, formsets, change)
            changed_data = set(getattr(form, "changed_data", ()))
            if not actor.is_superuser or not changed_data.intersection(
                {"groups", "user_permissions"}
            ):
                return
            user = form.instance
            groups = sorted(user.groups.values_list("name", flat=True))
            explicit_permissions = sorted(
                f"{permission.content_type.app_label}.{permission.codename}"
                for permission in user.user_permissions.select_related("content_type")
            )
            append_audit_event(
                actor=actor,
                action="account.authorization_assignments_updated",
                object_type="accounts.User",
                object_id=str(user.pk),
                summary="Superuser changed staff role or explicit permission assignments.",
                metadata={
                    "groups": groups,
                    "explicitPermissions": explicit_permissions,
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
