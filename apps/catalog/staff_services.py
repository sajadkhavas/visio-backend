from __future__ import annotations

from typing import TypeVar

from django.db import models, transaction

from apps.accounts.models import User
from apps.operations.audit import append_audit_event
from apps.operations.permissions import require_staff_permission

ModelT = TypeVar("ModelT", bound=models.Model)


def save_catalog_object_as_staff(
    actor: User,
    obj: ModelT,
    *,
    change: bool,
) -> ModelT:
    model_name = obj._meta.model_name
    if not model_name:
        raise ValueError("Catalog model must have a Django model name.")

    action = "change" if change else "add"
    require_staff_permission(actor, f"catalog.{action}_{model_name}")

    with transaction.atomic():
        obj.full_clean()
        obj.save()
        append_audit_event(
            actor=actor,
            action="catalog.updated" if change else "catalog.created",
            object_type=f"{obj._meta.app_label}.{obj._meta.object_name}",
            object_id=str(obj.pk),
            summary="Catalog mutation through the controlled staff service boundary.",
            metadata={"change": change},
        )
    return obj
