from __future__ import annotations

from dataclasses import dataclass

from django.contrib.auth.models import Group, Permission
from django.db import transaction

PermissionKey = tuple[str, str]


@dataclass(frozen=True)
class StaffRole:
    name: str
    permissions: tuple[PermissionKey, ...]


CATALOG_MODELS = (
    "brand",
    "category",
    "product",
    "productoption",
    "productoptionvalue",
    "productvariant",
    "productvariantoption",
    "productmedia",
    "productbadge",
)


def _model_permissions(app_label: str, model: str, actions: tuple[str, ...]) -> tuple[PermissionKey, ...]:
    return tuple((app_label, f"{action}_{model}") for action in actions)


CATALOG_EDITOR_PERMISSIONS = tuple(
    permission
    for model in CATALOG_MODELS
    for permission in _model_permissions("catalog", model, ("view", "add", "change"))
)

ROLE_MATRIX: tuple[StaffRole, ...] = (
    StaffRole(
        name="VISIO Catalog Manager",
        permissions=(
            *CATALOG_EDITOR_PERMISSIONS,
            *_model_permissions("commerce", "variantprice", ("view", "add", "change")),
            *_model_permissions("commerce", "variantinventory", ("view", "add", "change")),
            *_model_permissions("commerce", "inventoryreservation", ("view",)),
        ),
    ),
    StaffRole(
        name="VISIO Content Editor",
        permissions=_model_permissions("content", "contententry", ("view", "add", "change")),
    ),
    StaffRole(
        name="VISIO Fulfillment Operator",
        permissions=(
            *_model_permissions("orders", "order", ("view", "change")),
            *_model_permissions("orders", "orderline", ("view",)),
            *_model_permissions("payments", "paymentattempt", ("view",)),
            *_model_permissions("payments", "paymentreconciliation", ("view",)),
            *_model_permissions("operations", "notificationoutbox", ("view", "change")),
            *_model_permissions("operations", "notificationdeliveryattempt", ("view",)),
            ("operations", "dispatch_notificationoutbox"),
        ),
    ),
    StaffRole(
        name="VISIO Finance Reviewer",
        permissions=(
            *_model_permissions("payments", "paymentattempt", ("view",)),
            *_model_permissions("payments", "paymentreconciliation", ("view",)),
            *_model_permissions("orders", "order", ("view",)),
            *_model_permissions("operations", "auditevent", ("view",)),
            ("operations", "verify_audit_chain"),
        ),
    ),
    StaffRole(
        name="VISIO Customer Support",
        permissions=(
            *_model_permissions("accounts", "user", ("view", "change")),
            *_model_permissions("accounts", "address", ("view",)),
            *_model_permissions("orders", "order", ("view",)),
            *_model_permissions("orders", "orderline", ("view",)),
            *_model_permissions("payments", "paymentattempt", ("view",)),
        ),
    ),
    StaffRole(
        name="VISIO Operations Admin",
        permissions=(
            *CATALOG_EDITOR_PERMISSIONS,
            *_model_permissions("commerce", "variantprice", ("view", "add", "change")),
            *_model_permissions("commerce", "variantinventory", ("view", "add", "change")),
            *_model_permissions("commerce", "inventoryreservation", ("view",)),
            *_model_permissions("content", "contententry", ("view", "add", "change")),
            *_model_permissions("orders", "order", ("view", "change")),
            *_model_permissions("orders", "orderline", ("view",)),
            *_model_permissions("payments", "paymentattempt", ("view",)),
            *_model_permissions("payments", "paymentreconciliation", ("view",)),
            *_model_permissions("accounts", "user", ("view", "change")),
            *_model_permissions("accounts", "address", ("view",)),
            *_model_permissions("operations", "auditevent", ("view",)),
            *_model_permissions("operations", "notificationoutbox", ("view", "change")),
            *_model_permissions("operations", "notificationdeliveryattempt", ("view",)),
            ("operations", "dispatch_notificationoutbox"),
            ("operations", "verify_audit_chain"),
        ),
    ),
)


def _resolve_permission(app_label: str, codename: str) -> Permission:
    try:
        return Permission.objects.select_related("content_type").get(
            content_type__app_label=app_label,
            codename=codename,
        )
    except Permission.DoesNotExist as exc:
        raise RuntimeError(f"Required permission {app_label}.{codename} does not exist.") from exc


def sync_staff_roles(*, dry_run: bool = False) -> dict[str, tuple[str, ...]]:
    resolved: dict[str, tuple[str, ...]] = {}
    with transaction.atomic():
        for role in ROLE_MATRIX:
            permissions = [_resolve_permission(app_label, codename) for app_label, codename in role.permissions]
            resolved[role.name] = tuple(
                sorted(f"{permission.content_type.app_label}.{permission.codename}" for permission in permissions)
            )
            if dry_run:
                continue
            group, _ = Group.objects.get_or_create(name=role.name)
            group.permissions.set(permissions)
        if dry_run:
            transaction.set_rollback(True)
    return resolved
