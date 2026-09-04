from __future__ import annotations

from typing import cast
from uuid import UUID

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import APIException, NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User

from .selectors import order_for_user, orders_for_user
from .serializers import OrderCreateSerializer, order_payload
from .services import (
    OrderConflictError,
    OrderNotFoundError,
    OrderStaleError,
    OrderTransitionError,
    cancel_order,
    create_order,
)


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request conflicts with current order state."
    default_code = "order_conflict"


def _user(request: Request) -> User:
    return cast(User, request.user)


class OrderCollectionView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        orders = orders_for_user(_user(request))
        return Response({"orders": [order_payload(order, include_lines=False) for order in orders]})

    @extend_schema(request=OrderCreateSerializer, responses={201: OpenApiTypes.OBJECT})
    def post(self, request: Request) -> Response:
        serializer = OrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            result = create_order(
                _user(request),
                checkout_id=cast(UUID, data["checkoutId"]),
                idempotency_key=cast(UUID, data["idempotencyKey"]),
            )
        except OrderNotFoundError as exc:
            raise NotFound(str(exc)) from exc
        except OrderConflictError as exc:
            raise Conflict(str(exc)) from exc
        except OrderStaleError as exc:
            raise ValidationError({"order": [str(exc)]}) from exc

        code = status.HTTP_201_CREATED if result.created else status.HTTP_200_OK
        order = order_for_user(_user(request), result.order.public_id)
        return Response({"order": order_payload(order, include_lines=True)}, status=code)


class OrderDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request, public_id: UUID) -> Response:
        try:
            order = order_for_user(_user(request), public_id)
        except OrderNotFoundError as exc:
            raise NotFound(str(exc)) from exc
        return Response({"order": order_payload(order, include_lines=True)})


class OrderCancelView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={200: OpenApiTypes.OBJECT})
    def post(self, request: Request, public_id: UUID) -> Response:
        try:
            cancel_order(_user(request), public_id)
            order = order_for_user(_user(request), public_id)
        except OrderNotFoundError as exc:
            raise NotFound(str(exc)) from exc
        except OrderTransitionError as exc:
            raise Conflict(str(exc)) from exc
        return Response({"order": order_payload(order, include_lines=True)})
