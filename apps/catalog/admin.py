from typing import Any

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import models, transaction
from django.http import HttpRequest

from apps.accounts.models import User
from apps.operations.audit import append_audit_event

from .models import (
    Brand,
    Category,
    Product,
    ProductBadge,
    ProductMedia,
    ProductOption,
    ProductOptionValue,
    ProductVariant,
    ProductVariantOption,
)


def _require_staff_user(request: HttpRequest) -> User:
    actor = request.user
    if not isinstance(actor, User) or not actor.is_staff:
        raise PermissionDenied("Authenticated staff user required for admin mutation.")
    return actor


class AuditedCatalogAdmin(admin.ModelAdmin):
    def has_delete_permission(self, request: HttpRequest, obj: models.Model | None = None) -> bool:
        return False

    def save_model(
        self,
        request: HttpRequest,
        obj: models.Model,
        form: Any,
        change: bool,
    ) -> None:
        actor = _require_staff_user(request)
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            append_audit_event(
                actor=actor,
                action="catalog.updated" if change else "catalog.created",
                object_type=f"{obj._meta.app_label}.{obj._meta.object_name}",
                object_id=str(obj.pk),
                summary="Catalog mutation through Django Admin.",
                metadata={"change": change},
            )


admin.site.register(Brand, AuditedCatalogAdmin)
admin.site.register(Category, AuditedCatalogAdmin)
admin.site.register(Product, AuditedCatalogAdmin)
admin.site.register(ProductOption, AuditedCatalogAdmin)
admin.site.register(ProductOptionValue, AuditedCatalogAdmin)
admin.site.register(ProductVariant, AuditedCatalogAdmin)
admin.site.register(ProductVariantOption, AuditedCatalogAdmin)
admin.site.register(ProductMedia, AuditedCatalogAdmin)
admin.site.register(ProductBadge, AuditedCatalogAdmin)
