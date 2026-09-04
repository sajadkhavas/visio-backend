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

from .serializers import (
    CheckoutCreateSerializer,
    CheckoutFinalizeSerializer,
    ShippingOptionsQuerySerializer,
    checkout_payload,
    shipping_quote_payload,
)
from .services import (
    AddressNotServiceableError,
    CheckoutConflictError,
    CheckoutNotFoundError,
    CheckoutStaleError,
    CheckoutUnavailableError,
    ShippingConfigurationError,
    TaxPolicyUnavailableError,
    cancel_checkout,
    create_checkout,
    finalize_checkout,
    get_current_checkout,
    shipping_quotes,
)


class Conflict(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The request conflicts with current checkout state."
    default_code = "checkout_conflict"


def _user(request: Request) -> User:
    return cast(User, request.user)


def _validation_error(exc: Exception) -> ValidationError:
    return ValidationError({"checkout": [str(exc)]})


class ShippingOptionsView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(
        parameters=[ShippingOptionsQuerySerializer],
        responses={200: OpenApiTypes.OBJECT},
    )
    def get(self, request: Request) -> Response:
        serializer = ShippingOptionsQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        address_id = int(serializer.validated_data["addressId"])
        try:
            quotes = shipping_quotes(_user(request), address_id)
        except CheckoutNotFoundError as exc:
            raise NotFound(str(exc)) from exc
        except (
            AddressNotServiceableError,
            CheckoutUnavailableError,
            ShippingConfigurationError,
            TaxPolicyUnavailableError,
        ) as exc:
            raise _validation_error(exc) from exc
        return Response({"options": [shipping_quote_payload(quote) for quote in quotes]})


class CurrentCheckoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        session = get_current_checkout(_user(request))
        return Response({"checkout": checkout_payload(session) if session is not None else None})


class CheckoutCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=CheckoutCreateSerializer, responses={201: OpenApiTypes.OBJECT})
    def post(self, request: Request) -> Response:
        serializer = CheckoutCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        try:
            session = create_checkout(
                _user(request),
                address_id=int(data["addressId"]),
                shipping_method_code=str(data["shippingMethodCode"]),
                idempotency_key=cast(UUID, data["idempotencyKey"]),
            )
        except CheckoutNotFoundError as exc:
            raise NotFound(str(exc)) from exc
        except CheckoutConflictError as exc:
            raise Conflict(str(exc)) from exc
        except (
            AddressNotServiceableError,
            CheckoutUnavailableError,
            ShippingConfigurationError,
            TaxPolicyUnavailableError,
        ) as exc:
            raise _validation_error(exc) from exc
        return Response({"checkout": checkout_payload(session)}, status=status.HTTP_201_CREATED)


class CheckoutFinalizeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=CheckoutFinalizeSerializer, responses={200: OpenApiTypes.OBJECT})
    def post(self, request: Request, checkout_id: UUID) -> Response:
        serializer = CheckoutFinalizeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            session = finalize_checkout(
                _user(request),
                checkout_id,
                idempotency_key=cast(UUID, serializer.validated_data["idempotencyKey"]),
            )
        except CheckoutNotFoundError as exc:
            raise NotFound(str(exc)) from exc
        except CheckoutConflictError as exc:
            raise Conflict(str(exc)) from exc
        except (
            AddressNotServiceableError,
            CheckoutStaleError,
            CheckoutUnavailableError,
            ShippingConfigurationError,
            TaxPolicyUnavailableError,
        ) as exc:
            raise _validation_error(exc) from exc
        return Response({"checkout": checkout_payload(session)})


class CheckoutCancelView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={200: OpenApiTypes.OBJECT})
    def post(self, request: Request, checkout_id: UUID) -> Response:
        try:
            session = cancel_checkout(_user(request), checkout_id)
        except CheckoutNotFoundError as exc:
            raise NotFound(str(exc)) from exc
        except CheckoutConflictError as exc:
            raise Conflict(str(exc)) from exc
        return Response({"checkout": checkout_payload(session)})
