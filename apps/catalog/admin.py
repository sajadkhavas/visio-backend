from typing import Any

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import models
from django.http import HttpRequest

from apps.accounts.models import User

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
from .staff_services import save_catalog_object_as_staff


def _staff_actor(request: HttpRequest) -> User:
    actor = request.user
    if not isinstance(actor, User):
        raise PermissionDenied("Authenticated VISIO staff user required.")
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
        del form
        save_catalog_object_as_staff(_staff_actor(request), obj, change=change)


admin.site.register(Brand, AuditedCatalogAdmin)
admin.site.register(Category, AuditedCatalogAdmin)
admin.site.register(Product, AuditedCatalogAdmin)
admin.site.register(ProductOption, AuditedCatalogAdmin)
admin.site.register(ProductOptionValue, AuditedCatalogAdmin)
admin.site.register(ProductVariant, AuditedCatalogAdmin)
admin.site.register(ProductVariantOption, AuditedCatalogAdmin)
admin.site.register(ProductMedia, AuditedCatalogAdmin)
admin.site.register(ProductBadge, AuditedCatalogAdmin)
