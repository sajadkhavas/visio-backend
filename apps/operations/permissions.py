from rest_framework.permissions import BasePermission
from rest_framework.request import Request


class HasOperationsViewPermission(BasePermission):
    message = "Operations staff permission is required."

    def has_permission(self, request: Request, view: object) -> bool:
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and getattr(user, "is_active", False)
            and getattr(user, "is_staff", False)
            and user.has_perm("operations.view_auditevent")
        )
