from __future__ import annotations

from typing import Any, cast
from uuid import UUID

from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import User

from .serializers import (
    BrowserCartImportSerializer,
    CartMutationSerializer,
    CartQuantitySerializer,
    CartValidateSerializer,
    WishlistResponseSerializer,
    cart_payload,
    wishlist_payload,
)
from .services import (
    BrowserCartLine,
    CartLineNotFoundError,
    CartNotFoundError,
    VariantNotPurchasableError,
    WishlistProductUnavailableError,
    add_cart_line,
    add_wishlist_product,
    clear_cart,
    get_or_create_active_cart,
    merge_browser_cart,
    remove_cart_line,
    remove_wishlist_product,
    set_cart_line_quantity,
    validate_and_clamp_cart,
)


def _user(request: Request) -> User:
    return cast(User, request.user)


def _snapshots_from_items(items: list[dict[str, Any]]) -> dict[UUID, dict[str, Any]]:
    snapshots: dict[UUID, dict[str, Any]] = {}
    for item in items:
        identity = item["identity"]
        variant_id = cast(UUID, identity["variantId"])
        snapshot = item.get("priceSnapshot")
        if isinstance(snapshot, dict):
            snapshots[variant_id] = snapshot
    return snapshots


def _cart_response(
    user: User,
    *,
    snapshots: dict[UUID, dict[str, Any]] | None = None,
    adjusted: dict[UUID, int] | None = None,
) -> Response:
    cart = get_or_create_active_cart(user)
    payload, issues = cart_payload(cart, snapshots=snapshots, adjusted=adjusted)
    return Response({"cart": payload, "issues": issues})


class CurrentCartView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: OpenApiTypes.OBJECT})
    def get(self, request: Request) -> Response:
        return _cart_response(_user(request))

    @extend_schema(request=None, responses={200: OpenApiTypes.OBJECT})
    def delete(self, request: Request) -> Response:
        clear_cart(_user(request))
        return _cart_response(_user(request))


class CartLineCreateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=CartMutationSerializer, responses={200: OpenApiTypes.OBJECT})
    def post(self, request: Request) -> Response:
        serializer = CartMutationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        variant_id = cast(UUID, data["variantId"])
        quantity = int(data["quantity"])
        try:
            add_cart_line(_user(request), variant_id, quantity=quantity)
        except VariantNotPurchasableError as exc:
            raise ValidationError({"variantId": [str(exc)]}) from exc

        snapshots: dict[UUID, dict[str, Any]] = {}
        snapshot = data.get("priceSnapshot")
        if isinstance(snapshot, dict):
            snapshots[variant_id] = snapshot
        return _cart_response(_user(request), snapshots=snapshots)


class CartLineDetailView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=CartQuantitySerializer, responses={200: OpenApiTypes.OBJECT})
    def patch(self, request: Request, variant_id: UUID) -> Response:
        serializer = CartQuantitySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            set_cart_line_quantity(
                _user(request),
                variant_id,
                quantity=int(serializer.validated_data["quantity"]),
            )
        except (CartNotFoundError, CartLineNotFoundError) as exc:
            raise NotFound(str(exc)) from exc
        return _cart_response(_user(request))

    @extend_schema(request=None, responses={200: OpenApiTypes.OBJECT})
    def delete(self, request: Request, variant_id: UUID) -> Response:
        try:
            remove_cart_line(_user(request), variant_id)
        except (CartNotFoundError, CartLineNotFoundError) as exc:
            raise NotFound(str(exc)) from exc
        return _cart_response(_user(request))


class CartValidateView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=CartValidateSerializer, responses={200: OpenApiTypes.OBJECT})
    def post(self, request: Request) -> Response:
        serializer = CartValidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        items = cast(list[dict[str, Any]], serializer.validated_data.get("items", []))
        snapshots = _snapshots_from_items(items)
        _cart, adjusted_pairs = validate_and_clamp_cart(_user(request))
        adjusted = {variant_id: allowed for variant_id, allowed in adjusted_pairs}
        return _cart_response(_user(request), snapshots=snapshots, adjusted=adjusted)


class CartImportView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=BrowserCartImportSerializer, responses={200: OpenApiTypes.OBJECT})
    def post(self, request: Request) -> Response:
        serializer = BrowserCartImportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        items = cast(list[dict[str, Any]], serializer.validated_data["items"])
        browser_lines = [
            BrowserCartLine(
                variant_id=cast(UUID, item["identity"]["variantId"]),
                quantity=int(item["quantity"]),
            )
            for item in items
        ]
        _cart, import_issues = merge_browser_cart(_user(request), browser_lines)
        snapshots = _snapshots_from_items(items)
        cart = get_or_create_active_cart(_user(request))
        payload, issues = cart_payload(cart, snapshots=snapshots)
        return Response(
            {
                "cart": payload,
                "issues": issues,
                "importIssues": [
                    {"variantId": str(issue.variant_id), "code": issue.code}
                    for issue in import_issues
                ],
            }
        )


class WishlistView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses={200: WishlistResponseSerializer})
    def get(self, request: Request) -> Response:
        return Response(wishlist_payload(_user(request).pk))


class WishlistItemView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={200: WishlistResponseSerializer})
    def put(self, request: Request, product_id: UUID) -> Response:
        try:
            add_wishlist_product(_user(request), product_id)
        except WishlistProductUnavailableError as exc:
            raise ValidationError({"productId": [str(exc)]}) from exc
        return Response(wishlist_payload(_user(request).pk), status=status.HTTP_200_OK)

    @extend_schema(request=None, responses={204: None})
    def delete(self, request: Request, product_id: UUID) -> Response:
        remove_wishlist_product(_user(request), product_id)
        return Response(status=status.HTTP_204_NO_CONTENT)
