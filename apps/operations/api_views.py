from typing import cast

from django.db.models import Count
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User
from apps.orders.models import Order
from apps.payments.models import PaymentReconciliation

from .models import AuditEvent, NotificationOutbox
from .permissions import HasOperationsViewPermission


class StaffMeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="staff_me",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        user = cast(User, request.user)
        if not user.is_active or not user.is_staff:
            raise PermissionDenied("Active VISIO staff access is required.")

        groups = sorted(
            user.groups.filter(name__startswith="VISIO ").values_list("name", flat=True)
        )
        permissions = sorted(user.get_all_permissions())
        return Response(
            {
                "id": user.pk,
                "email": user.email,
                "firstName": user.first_name,
                "lastName": user.last_name,
                "isStaff": user.is_staff,
                "isSuperuser": user.is_superuser,
                "groups": groups,
                "permissions": permissions,
            }
        )


class OperationsSummaryView(APIView):
    permission_classes = [HasOperationsViewPermission]

    @extend_schema(
        operation_id="staff_operations_summary",
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        order_counts = {
            row["status"]: row["count"]
            for row in Order.objects.values("status").annotate(count=Count("id")).order_by()
        }
        return Response(
            {
                "orders": order_counts,
                "paymentReconciliationMismatches": PaymentReconciliation.objects.filter(
                    status=PaymentReconciliation.Status.MISMATCH
                ).count(),
                "notifications": {
                    "pending": NotificationOutbox.objects.filter(
                        status=NotificationOutbox.Status.PENDING
                    ).count(),
                    "failed": NotificationOutbox.objects.filter(
                        status=NotificationOutbox.Status.FAILED
                    ).count(),
                },
                "auditEvents": AuditEvent.objects.count(),
            }
        )
