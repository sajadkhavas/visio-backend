from __future__ import annotations

from typing import cast
from uuid import UUID

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User

from .selectors import payment_attempt_for_user
from .serializers import PaymentCallbackSerializer, PaymentStartSerializer, payment_payload
from .services import (
    PaymentConfigurationError,
    PaymentConflictError,
    PaymentNotFoundError,
    PaymentProviderError,
    process_callback,
    start_payment,
)


class PaymentConflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request conflicts with current payment state."
    default_code = "payment_conflict"


class PaymentUnavailable(APIException):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    default_detail = "Payment service is unavailable."
    default_code = "payment_unavailable"


class PaymentUpstreamFailure(APIException):
    status_code = status.HTTP_502_BAD_GATEWAY
    default_detail = "Payment provider request failed."
    default_code = "payment_provider_failure"


def _user(request: Request) -> User:
    return cast(User, request.user)


class PaymentCollectionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        operation_id="payments_create",
        request=PaymentStartSerializer,
        responses={200: OpenApiTypes.OBJECT, 201: OpenApiTypes.OBJECT},
    )
    def post(self, request: Request) -> Response:
        serializer = PaymentStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            result = start_payment(
                _user(request),
                order_public_id=cast(UUID, data["orderId"]),
                idempotency_key=cast(UUID, data["idempotencyKey"]),
            )
        except PaymentNotFoundError as exc:
            raise NotFound(str(exc)) from exc
        except PaymentConflictError as exc:
            raise PaymentConflict(str(exc)) from exc
        except PaymentConfigurationError as exc:
            raise PaymentUnavailable(str(exc)) from exc
        except PaymentProviderError as exc:
            raise PaymentUpstreamFailure(str(exc)) from exc

        attempt = payment_attempt_for_user(_user(request), result.attempt.id)
        code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
        return Response({"payment": payment_payload(attempt)}, status=code)


class PaymentDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id="payments_retrieve", responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request, attempt_id: UUID) -> Response:
        try:
            attempt = payment_attempt_for_user(_user(request), attempt_id)
        except PaymentNotFoundError as exc:
            raise NotFound(str(exc)) from exc
        return Response({"payment": payment_payload(attempt)})


class ZarinPalCallbackView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[type] = []

    @extend_schema(
        operation_id="payments_zarinpal_callback",
        parameters=[],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        serializer = PaymentCallbackSerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            outcome = process_callback(
                authority=cast(str, data["Authority"]),
                callback_status=cast(str, data["Status"]),
            )
        except PaymentNotFoundError as exc:
            raise NotFound(str(exc)) from exc
        except PaymentConflictError as exc:
            raise PaymentConflict(str(exc)) from exc
        except PaymentConfigurationError as exc:
            raise PaymentUnavailable(str(exc)) from exc
        except PaymentProviderError as exc:
            raise PaymentUpstreamFailure(str(exc)) from exc

        return Response(
            {
                "paymentId": str(outcome.attempt.id),
                "orderId": str(outcome.attempt.order.public_id),
                "status": outcome.attempt.status,
                "orderConfirmed": outcome.order_confirmed,
                "reconciliationRequired": outcome.reconciliation_required,
            }
        )
