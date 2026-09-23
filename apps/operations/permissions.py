from collections.abc import Iterable
from typing import Any

from django.core.exceptions import PermissionDenied
from rest_framework.permissions import BasePermission
from rest_framework.request import Request

from apps.accounts.models import User


def staff_has_permissions(user: Any, permissions: Iterable[str] = ()) -> bool:
    required = tuple(permissions)
    return bool(
        user
        and getattr(user, "is_authenticated", False)
        and getattr(user, "is_active", False)
        and getattr(user, "is_staff", False)
        and all(user.has_perm(permission) for permission in required)
    )


def require_staff_permission(actor: User, permission: str) -> None:
    if not staff_has_permissions(actor, (permission,)):
        raise PermissionDenied(f"Missing staff permission: {permission}")


class HasStaffPermissions(BasePermission):
    message = "VISIO staff permission is required."
    required_permissions: tuple[str, ...] = ()

    def has_permission(self, request: Request, view: object) -> bool:
        required = getattr(view, "required_staff_permissions", self.required_permissions)
        return staff_has_permissions(request.user, required)


class HasOperationsViewPermission(HasStaffPermissions):
    message = "Operations staff permission is required."
    required_permissions = ("operations.view_auditevent",)
