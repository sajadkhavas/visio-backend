from __future__ import annotations

from datetime import timedelta
from uuid import UUID

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from .models import InventoryReservation, VariantInventory

DEFAULT_RESERVATION_TTL = timedelta(minutes=15)


class InventoryUnavailableError(Exception):
    """Raised when authoritative inventory cannot satisfy a requested mutation."""


class ReservationStateError(Exception):
    """Raised when a reservation transition is not valid from its current state."""


def _reserved_quantity(inventory: VariantInventory, *, at: object) -> int:
    total = (
        inventory.reservations.filter(
            status=InventoryReservation.Status.ACTIVE,
            expires_at__gt=at,
        ).aggregate(total=Sum("quantity"))["total"]
        or 0
    )
    return int(total)


def _expire_stale_locked(inventory: VariantInventory, *, at: object) -> int:
    return int(
        inventory.reservations.filter(
            status=InventoryReservation.Status.ACTIVE,
            expires_at__lte=at,
        ).update(status=InventoryReservation.Status.EXPIRED, updated_at=at)
    )


def available_quantity(inventory: VariantInventory, *, at: object | None = None) -> int:
    now = at or timezone.now()
    reserved = _reserved_quantity(inventory, at=now)
    available = inventory.on_hand - reserved
    if available < 0:
        raise InventoryUnavailableError("Inventory reservations exceed on-hand quantity.")
    return available


def reserve_variant(
    variant_id: UUID,
    *,
    quantity: int,
    ttl: timedelta = DEFAULT_RESERVATION_TTL,
    at: object | None = None,
) -> InventoryReservation:
    if quantity <= 0:
        raise ValueError("Reservation quantity must be positive.")
    if ttl <= timedelta(0):
        raise ValueError("Reservation TTL must be positive.")

    now = at or timezone.now()
    with transaction.atomic():
        inventory = (
            VariantInventory.objects.select_for_update()
            .select_related("variant")
            .get(variant_id=variant_id)
        )
        if not inventory.is_active or not inventory.variant.is_active:
            raise InventoryUnavailableError("Inventory is not active for this variant.")

        _expire_stale_locked(inventory, at=now)
        available = available_quantity(inventory, at=now)
        if quantity > available:
            raise InventoryUnavailableError("Requested quantity exceeds available inventory.")

        return InventoryReservation.objects.create(
            inventory=inventory,
            quantity=quantity,
            status=InventoryReservation.Status.ACTIVE,
            expires_at=now + ttl,
        )


def _reservation_inventory_id(reservation_id: UUID) -> UUID:
    return UUID(
        str(
            InventoryReservation.objects.only("inventory_id")
            .get(pk=reservation_id)
            .inventory_id
        )
    )


def release_reservation(
    reservation_id: UUID,
    *,
    at: object | None = None,
) -> InventoryReservation:
    now = at or timezone.now()
    inventory_id = _reservation_inventory_id(reservation_id)

    with transaction.atomic():
        inventory = VariantInventory.objects.select_for_update().get(pk=inventory_id)
        _expire_stale_locked(inventory, at=now)
        reservation = InventoryReservation.objects.select_for_update().get(pk=reservation_id)

        if reservation.status in {
            InventoryReservation.Status.RELEASED,
            InventoryReservation.Status.EXPIRED,
        }:
            return reservation
        if reservation.status == InventoryReservation.Status.CONSUMED:
            raise ReservationStateError("Consumed reservation cannot be released.")

        reservation.status = InventoryReservation.Status.RELEASED
        reservation.updated_at = now
        reservation.save(update_fields=("status", "updated_at"))
        return reservation


def consume_reservation(
    reservation_id: UUID,
    *,
    at: object | None = None,
) -> InventoryReservation:
    now = at or timezone.now()
    inventory_id = _reservation_inventory_id(reservation_id)

    with transaction.atomic():
        inventory = VariantInventory.objects.select_for_update().get(pk=inventory_id)
        _expire_stale_locked(inventory, at=now)
        reservation = InventoryReservation.objects.select_for_update().get(pk=reservation_id)

        if reservation.status != InventoryReservation.Status.ACTIVE:
            raise ReservationStateError(
                f"Reservation in state {reservation.status!r} cannot be consumed."
            )
        if reservation.expires_at <= now:
            reservation.status = InventoryReservation.Status.EXPIRED
            reservation.updated_at = now
            reservation.save(update_fields=("status", "updated_at"))
            raise ReservationStateError("Expired reservation cannot be consumed.")
        if inventory.on_hand < reservation.quantity:
            raise InventoryUnavailableError("On-hand quantity is below the reserved quantity.")

        inventory.on_hand -= reservation.quantity
        inventory.save(update_fields=("on_hand", "updated_at"))
        reservation.status = InventoryReservation.Status.CONSUMED
        reservation.updated_at = now
        reservation.save(update_fields=("status", "updated_at"))
        return reservation


def set_on_hand(
    variant_id: UUID,
    *,
    quantity: int,
    at: object | None = None,
) -> VariantInventory:
    if quantity < 0:
        raise ValueError("On-hand quantity cannot be negative.")

    now = at or timezone.now()
    with transaction.atomic():
        inventory = VariantInventory.objects.select_for_update().get(variant_id=variant_id)
        _expire_stale_locked(inventory, at=now)
        reserved = _reserved_quantity(inventory, at=now)
        if quantity < reserved:
            raise InventoryUnavailableError(
                "On-hand quantity cannot be set below active reserved quantity."
            )
        inventory.on_hand = quantity
        inventory.updated_at = now
        inventory.save(update_fields=("on_hand", "updated_at"))
        return inventory
