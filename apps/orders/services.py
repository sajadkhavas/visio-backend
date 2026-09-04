from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.cart.models import Cart
from apps.catalog.models import ProductVariantOption
from apps.checkout.models import CheckoutLine, CheckoutSession
from apps.checkout.order_bridge import revalidate_ready_checkout
from apps.checkout.services import CheckoutError, CheckoutNotFoundError
from apps.commerce.models import InventoryReservation
from apps.commerce.services import consume_reservation, release_reservation

from .models import Order, OrderLine


class OrderError(Exception):
    """Base class for B06 order-domain failures."""


class OrderNotFoundError(OrderError):
    pass


class OrderConflictError(OrderError):
    pass


class OrderStaleError(OrderError):
    pass


class OrderTransitionError(OrderError):
    pass


@dataclass(frozen=True)
class OrderCreationResult:
    order: Order
    created: bool


FULFILLMENT_TRANSITIONS: dict[str, str] = {
    Order.Status.CONFIRMED: Order.Status.PROCESSING,
    Order.Status.PROCESSING: Order.Status.SHIPPED,
    Order.Status.SHIPPED: Order.Status.DELIVERED,
}


def customer_snapshot(user: User) -> dict[str, Any]:
    return {
        "userId": user.pk,
        "email": user.email,
        "username": user.username,
    }


def _option_snapshots(variant_ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    selections = list(
        ProductVariantOption.objects.select_for_update()
        .filter(variant_id__in=variant_ids)
        .select_related("option", "value")
        .order_by("variant_id", "option__position", "option__key", "id")
    )
    snapshots: dict[UUID, dict[str, Any]] = defaultdict(dict)
    for selection in selections:
        variant_id = UUID(str(selection.variant_id))
        snapshots[variant_id][selection.option.key] = {
            "value": selection.value.value,
            "label": selection.value.label,
            "optionLabel": selection.option.label,
        }
    return dict(snapshots)


def _locked_checkout_lines(checkout: CheckoutSession) -> list[CheckoutLine]:
    return list(
        CheckoutLine.objects.select_for_update()
        .filter(checkout=checkout)
        .select_related("variant", "variant__product", "reservation", "reservation__inventory")
        .order_by("variant_id", "id")
    )


def _validate_checkout_lines(checkout: CheckoutSession, *, at: datetime) -> list[CheckoutLine]:
    lines = _locked_checkout_lines(checkout)
    if not lines:
        raise OrderStaleError("READY checkout has no durable checkout lines.")

    subtotal = 0
    for line in lines:
        reservation = line.reservation
        if reservation.status != InventoryReservation.Status.ACTIVE:
            raise OrderStaleError("Checkout reservation is no longer active.")
        if reservation.expires_at <= at:
            raise OrderStaleError("Checkout reservation has expired.")
        if reservation.quantity != line.quantity:
            raise OrderStaleError("Checkout reservation quantity does not match its line.")
        if reservation.inventory.variant_id != line.variant_id:
            raise OrderStaleError("Checkout reservation variant does not match its line.")
        if int(line.line_total_toman) != int(line.unit_price_toman) * line.quantity:
            raise OrderStaleError("Checkout line monetary snapshot is inconsistent.")
        subtotal += int(line.line_total_toman)

    if subtotal != int(checkout.subtotal_toman):
        raise OrderStaleError("Checkout line subtotal does not match checkout totals.")
    return lines


def _existing_order_for_request(
    user: User,
    *,
    checkout_id: UUID,
    idempotency_key: UUID,
) -> Order | None:
    by_key = (
        Order.objects.select_for_update()
        .filter(user=user, idempotency_key=idempotency_key)
        .first()
    )
    if by_key is not None:
        if by_key.checkout_id != checkout_id:
            raise OrderConflictError(
                "This order idempotency key was already used for another checkout."
            )
        return by_key

    return Order.objects.select_for_update().filter(user=user, checkout_id=checkout_id).first()


def create_order(
    user: User,
    *,
    checkout_id: UUID,
    idempotency_key: UUID,
    at: datetime | None = None,
) -> OrderCreationResult:
    now = at or timezone.now()

    with transaction.atomic():
        User.objects.select_for_update().only("pk").get(pk=user.pk)
        existing = _existing_order_for_request(
            user,
            checkout_id=checkout_id,
            idempotency_key=idempotency_key,
        )
        if existing is not None:
            return OrderCreationResult(order=existing, created=False)

        try:
            checkout = revalidate_ready_checkout(user, checkout_id, at=now)
        except CheckoutNotFoundError as exc:
            raise OrderNotFoundError(str(exc)) from exc
        except CheckoutError as exc:
            raise OrderStaleError(str(exc)) from exc

        cart = Cart.objects.select_for_update().get(
            pk=checkout.cart_id,
            user=user,
            status=Cart.Status.ACTIVE,
        )
        if cart.revision != checkout.cart_revision:
            raise OrderStaleError("Cart revision changed after checkout finalization.")

        checkout_lines = _validate_checkout_lines(checkout, at=now)
        variant_ids = [UUID(str(line.variant_id)) for line in checkout_lines]
        options_by_variant = _option_snapshots(variant_ids)

        order = Order.objects.create(
            user=user,
            checkout=checkout,
            idempotency_key=idempotency_key,
            status=Order.Status.PENDING_PAYMENT,
            status_changed_at=now,
            customer_snapshot=customer_snapshot(user),
            address_snapshot=deepcopy(checkout.address_snapshot),
            shipping_snapshot=deepcopy(checkout.shipping_snapshot),
            subtotal_toman=checkout.subtotal_toman,
            discount_toman=checkout.discount_toman,
            shipping_toman=checkout.shipping_toman,
            tax_toman=checkout.tax_toman,
            payable_toman=checkout.payable_toman,
            tax_rate_bps=checkout.tax_rate_bps,
        )

        for checkout_line in checkout_lines:
            variant = checkout_line.variant
            product = variant.product
            variant_id = UUID(str(variant.pk))
            OrderLine.objects.create(
                order=order,
                reservation=checkout_line.reservation,
                source_product_id=product.pk,
                source_product_slug=product.slug,
                source_product_name=product.name,
                source_variant_id=variant.pk,
                source_variant_sku=variant.sku,
                option_snapshot=deepcopy(options_by_variant.get(variant_id, {})),
                quantity=checkout_line.quantity,
                unit_price_toman=checkout_line.unit_price_toman,
                line_total_toman=checkout_line.line_total_toman,
            )

        cart.status = Cart.Status.CONVERTED
        cart.revision += 1
        cart.updated_at = now
        cart.save(update_fields=("status", "revision", "updated_at"))

        checkout.status = CheckoutSession.Status.COMPLETED
        checkout.updated_at = now
        checkout.save(update_fields=("status", "updated_at"))
        return OrderCreationResult(order=order, created=True)


def _locked_order_by_id(order_id: UUID) -> Order:
    try:
        return Order.objects.select_for_update().get(pk=order_id)
    except Order.DoesNotExist as exc:
        raise OrderNotFoundError("Order does not exist.") from exc


def _locked_owned_order(user: User, public_id: UUID) -> Order:
    try:
        return Order.objects.select_for_update().get(user=user, public_id=public_id)
    except Order.DoesNotExist as exc:
        raise OrderNotFoundError("Order does not exist for this user.") from exc


def _order_lines_for_transition(order: Order) -> list[OrderLine]:
    return list(
        OrderLine.objects.select_for_update()
        .filter(order=order)
        .select_related("reservation")
        .order_by("source_variant_id", "id")
    )


def _set_status(order: Order, status: str, *, at: datetime) -> Order:
    order.status = status
    order.status_changed_at = at
    order.updated_at = at
    order.save(update_fields=("status", "status_changed_at", "updated_at"))
    return order


def confirm_order_after_verified_payment(
    order_id: UUID,
    *,
    at: datetime | None = None,
) -> Order:
    """Internal B07 handoff. Call only after provider payment truth is verified."""

    now = at or timezone.now()
    with transaction.atomic():
        order = _locked_order_by_id(order_id)
        if order.status in {
            Order.Status.CONFIRMED,
            Order.Status.PROCESSING,
            Order.Status.SHIPPED,
            Order.Status.DELIVERED,
        }:
            return order
        if order.status != Order.Status.PENDING_PAYMENT:
            raise OrderTransitionError(
                f"Order in state {order.status!r} cannot be payment-confirmed."
            )

        lines = _order_lines_for_transition(order)
        if not lines:
            raise OrderStaleError("Order has no lines to confirm.")
        for line in lines:
            consume_reservation(line.reservation_id, at=now)
        return _set_status(order, Order.Status.CONFIRMED, at=now)


def cancel_order(
    user: User,
    public_id: UUID,
    *,
    at: datetime | None = None,
) -> Order:
    now = at or timezone.now()
    with transaction.atomic():
        User.objects.select_for_update().only("pk").get(pk=user.pk)
        order = _locked_owned_order(user, public_id)
        if order.status == Order.Status.CANCELLED:
            return order
        if order.status != Order.Status.PENDING_PAYMENT:
            raise OrderTransitionError("Only a pending-payment order can be cancelled by its customer.")

        for line in _order_lines_for_transition(order):
            release_reservation(line.reservation_id, at=now)
        return _set_status(order, Order.Status.CANCELLED, at=now)


def expire_order(order_id: UUID, *, at: datetime | None = None) -> Order:
    now = at or timezone.now()
    with transaction.atomic():
        order = _locked_order_by_id(order_id)
        if order.status == Order.Status.EXPIRED:
            return order
        if order.status != Order.Status.PENDING_PAYMENT:
            raise OrderTransitionError("Only a pending-payment order can expire.")

        for line in _order_lines_for_transition(order):
            release_reservation(line.reservation_id, at=now)
        return _set_status(order, Order.Status.EXPIRED, at=now)


def advance_fulfillment(
    order_id: UUID,
    *,
    target_status: str,
    at: datetime | None = None,
) -> Order:
    now = at or timezone.now()
    with transaction.atomic():
        order = _locked_order_by_id(order_id)
        if order.status == target_status:
            return order
        allowed_target = FULFILLMENT_TRANSITIONS.get(order.status)
        if allowed_target != target_status:
            raise OrderTransitionError(
                f"Transition {order.status!r} -> {target_status!r} is not allowed."
            )
        return _set_status(order, target_status, at=now)
