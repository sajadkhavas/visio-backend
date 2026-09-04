from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Any
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import Address, User
from apps.cart.models import Cart, CartLine
from apps.catalog.models import Product
from apps.commerce.models import InventoryReservation, VariantInventory, VariantPrice
from apps.commerce.services import (
    DEFAULT_RESERVATION_TTL,
    InventoryUnavailableError,
    release_reservation,
    reserve_variant,
)

from .models import CheckoutLine, CheckoutSession, CheckoutTaxPolicy, ShippingMethod, ShippingZone


class CheckoutError(Exception):
    """Base class for B05 checkout-domain failures."""


class CheckoutNotFoundError(CheckoutError):
    pass


class CheckoutConflictError(CheckoutError):
    pass


class CheckoutStaleError(CheckoutError):
    pass


class CheckoutUnavailableError(CheckoutError):
    pass


class AddressNotServiceableError(CheckoutError):
    pass


class ShippingConfigurationError(CheckoutError):
    pass


class TaxPolicyUnavailableError(CheckoutError):
    pass


@dataclass(frozen=True)
class PricedCartLine:
    line: CartLine
    unit_price_toman: int


@dataclass(frozen=True)
class ShippingQuote:
    method: ShippingMethod
    subtotal_toman: int
    discount_toman: int
    shipping_toman: int
    tax_toman: int
    payable_toman: int
    tax_rate_bps: int


def _normalized_scope(value: str) -> str:
    return value.strip().casefold()


def address_snapshot(address: Address) -> dict[str, Any]:
    return {
        "id": address.pk,
        "recipientName": address.recipient_name,
        "recipientPhone": address.recipient_phone,
        "countryCode": address.country_code,
        "province": address.province,
        "city": address.city,
        "postalCode": address.postal_code,
        "addressLine1": address.address_line1,
        "addressLine2": address.address_line2,
    }


def shipping_snapshot(method: ShippingMethod) -> dict[str, Any]:
    return {
        "id": str(method.pk),
        "code": method.code,
        "name": method.name,
        "zoneCode": method.zone.code,
        "deliveryMinDays": method.delivery_min_days,
        "deliveryMaxDays": method.delivery_max_days,
    }


def _shipping_amount(method: ShippingMethod, *, subtotal_toman: int) -> int:
    free_over = method.free_over_toman
    if free_over is not None and subtotal_toman >= int(free_over):
        return 0
    return int(method.flat_rate_toman)


def _tax_amount(
    *,
    subtotal_toman: int,
    shipping_toman: int,
    policy: CheckoutTaxPolicy,
) -> int:
    taxable_toman = subtotal_toman
    if policy.applies_to_shipping:
        taxable_toman += shipping_toman
    raw = Decimal(taxable_toman) * Decimal(policy.rate_bps) / Decimal(10_000)
    return int(raw.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _resolve_zone(address: Address, *, lock: bool) -> ShippingZone:
    queryset = ShippingZone.objects.filter(
        is_active=True,
        country_code__iexact=address.country_code.strip(),
    )
    if lock:
        queryset = queryset.select_for_update()

    province = _normalized_scope(address.province)
    city = _normalized_scope(address.city)
    matches: list[tuple[int, ShippingZone]] = []
    for zone in queryset.order_by("code", "id"):
        zone_province = _normalized_scope(zone.province)
        zone_city = _normalized_scope(zone.city)
        if zone_province and zone_province != province:
            continue
        if zone_city and zone_city != city:
            continue
        specificity = 2 if zone_city else 1 if zone_province else 0
        matches.append((specificity, zone))

    if not matches:
        raise AddressNotServiceableError("No active shipping zone serves this address.")

    best_specificity = max(item[0] for item in matches)
    best = [zone for specificity, zone in matches if specificity == best_specificity]
    if len(best) != 1:
        raise ShippingConfigurationError("Shipping zone configuration is ambiguous for this address.")
    return best[0]


def _active_tax_policy(country_code: str, *, lock: bool) -> CheckoutTaxPolicy:
    queryset = CheckoutTaxPolicy.objects.filter(
        is_active=True,
        country_code__iexact=country_code.strip(),
    )
    if lock:
        queryset = queryset.select_for_update()
    policies = list(queryset.order_by("id")[:2])
    if not policies:
        raise TaxPolicyUnavailableError("No active tax policy is configured for this destination.")
    if len(policies) != 1:
        raise TaxPolicyUnavailableError("Tax policy configuration is ambiguous for this destination.")
    return policies[0]


def _method_for_zone(zone: ShippingZone, method_code: str, *, lock: bool) -> ShippingMethod:
    queryset = ShippingMethod.objects.filter(zone=zone, is_active=True)
    if lock:
        queryset = queryset.select_for_update()
    code = method_code.strip().casefold()
    matches = [method for method in queryset.order_by("sort_order", "code", "id") if method.code.casefold() == code]
    if not matches:
        raise ShippingConfigurationError("Selected shipping method is not active for this address.")
    if len(matches) != 1:
        raise ShippingConfigurationError("Shipping method configuration is ambiguous.")
    return matches[0]


def _methods_for_zone(zone: ShippingZone, *, lock: bool) -> list[ShippingMethod]:
    queryset = ShippingMethod.objects.filter(zone=zone, is_active=True)
    if lock:
        queryset = queryset.select_for_update()
    methods = list(queryset.order_by("sort_order", "code", "id"))
    folded: set[str] = set()
    for method in methods:
        key = method.code.casefold()
        if key in folded:
            raise ShippingConfigurationError("Shipping method configuration is ambiguous.")
        folded.add(key)
    return methods


def _owned_address(user: User, address_id: int, *, lock: bool) -> Address:
    queryset = Address.objects.filter(user=user, pk=address_id)
    if lock:
        queryset = queryset.select_for_update()
    try:
        return queryset.get()
    except Address.DoesNotExist as exc:
        raise CheckoutNotFoundError("Address does not exist for this user.") from exc


def _locked_cart_and_prices(user: User) -> tuple[Cart, list[PricedCartLine], int]:
    try:
        cart = Cart.objects.select_for_update().get(user=user, status=Cart.Status.ACTIVE)
    except Cart.DoesNotExist as exc:
        raise CheckoutUnavailableError("An active cart is required for checkout.") from exc

    lines = list(
        CartLine.objects.select_for_update()
        .filter(cart=cart)
        .select_related("variant", "variant__product")
        .order_by("variant_id")
    )
    if not lines:
        raise CheckoutUnavailableError("Checkout cannot start from an empty cart.")

    variant_ids = [line.variant_id for line in lines]
    prices = list(
        VariantPrice.objects.select_for_update()
        .filter(variant_id__in=variant_ids, is_active=True)
        .order_by("variant_id")
    )
    price_by_variant = {price.variant_id: price for price in prices}

    priced: list[PricedCartLine] = []
    subtotal = 0
    for line in lines:
        variant = line.variant
        if not variant.is_active or variant.product.status != Product.Status.PUBLISHED:
            raise CheckoutUnavailableError("Cart contains a variant that is no longer purchasable.")
        price = price_by_variant.get(line.variant_id)
        if price is None:
            raise CheckoutUnavailableError("Cart contains a variant without active server price truth.")
        unit_price = int(price.amount_toman)
        priced.append(PricedCartLine(line=line, unit_price_toman=unit_price))
        subtotal += unit_price * line.quantity

    return cart, priced, subtotal


def _quote(
    method: ShippingMethod,
    *,
    subtotal_toman: int,
    policy: CheckoutTaxPolicy,
) -> ShippingQuote:
    discount_toman = 0
    shipping_toman = _shipping_amount(method, subtotal_toman=subtotal_toman)
    tax_toman = _tax_amount(
        subtotal_toman=subtotal_toman,
        shipping_toman=shipping_toman,
        policy=policy,
    )
    payable_toman = subtotal_toman - discount_toman + shipping_toman + tax_toman
    return ShippingQuote(
        method=method,
        subtotal_toman=subtotal_toman,
        discount_toman=discount_toman,
        shipping_toman=shipping_toman,
        tax_toman=tax_toman,
        payable_toman=payable_toman,
        tax_rate_bps=policy.rate_bps,
    )


def shipping_quotes(user: User, address_id: int) -> list[ShippingQuote]:
    with transaction.atomic():
        User.objects.select_for_update().only("pk").get(pk=user.pk)
        address = _owned_address(user, address_id, lock=True)
        _cart, _lines, subtotal = _locked_cart_and_prices(user)
        zone = _resolve_zone(address, lock=True)
        policy = _active_tax_policy(address.country_code, lock=True)
        methods = _methods_for_zone(zone, lock=True)
        if not methods:
            raise ShippingConfigurationError("No active shipping method is configured for this address.")
        return [_quote(method, subtotal_toman=subtotal, policy=policy) for method in methods]


def _release_session_reservations(session: CheckoutSession, *, at: datetime) -> None:
    lines = list(
        CheckoutLine.objects.filter(checkout=session)
        .select_related("reservation")
        .order_by("variant_id")
    )
    for line in lines:
        release_reservation(line.reservation_id, at=at)


def _terminate_session(
    session: CheckoutSession,
    *,
    status: str,
    at: datetime,
) -> CheckoutSession:
    if session.status in {CheckoutSession.Status.ACTIVE, CheckoutSession.Status.READY}:
        _release_session_reservations(session, at=at)
        session.status = status
        session.updated_at = at
        session.save(update_fields=("status", "updated_at"))
    return session


def create_checkout(
    user: User,
    *,
    address_id: int,
    shipping_method_code: str,
    idempotency_key: UUID,
    at: datetime | None = None,
) -> CheckoutSession:
    now = at or timezone.now()
    method_code = shipping_method_code.strip()
    if not method_code:
        raise ShippingConfigurationError("Shipping method code is required.")

    with transaction.atomic():
        User.objects.select_for_update().only("pk").get(pk=user.pk)
        existing = (
            CheckoutSession.objects.select_for_update()
            .select_related("shipping_method")
            .filter(user=user, idempotency_key=idempotency_key)
            .first()
        )
        if existing is not None:
            original_code = str(existing.shipping_snapshot.get("code", ""))
            if existing.address_id != address_id or original_code.casefold() != method_code.casefold():
                raise CheckoutConflictError(
                    "This checkout idempotency key was already used with different inputs."
                )
            return existing

        current_sessions = list(
            CheckoutSession.objects.select_for_update()
            .filter(
                user=user,
                status__in=(CheckoutSession.Status.ACTIVE, CheckoutSession.Status.READY),
            )
            .order_by("created_at", "id")
        )
        for current in current_sessions:
            _terminate_session(current, status=CheckoutSession.Status.CANCELLED, at=now)

        address = _owned_address(user, address_id, lock=True)
        cart, priced_lines, subtotal = _locked_cart_and_prices(user)
        zone = _resolve_zone(address, lock=True)
        method = _method_for_zone(zone, method_code, lock=True)
        tax_policy = _active_tax_policy(address.country_code, lock=True)
        quote = _quote(method, subtotal_toman=subtotal, policy=tax_policy)
        expires_at = now + DEFAULT_RESERVATION_TTL

        checkout = CheckoutSession.objects.create(
            user=user,
            cart=cart,
            address=address,
            shipping_method=method,
            idempotency_key=idempotency_key,
            status=CheckoutSession.Status.ACTIVE,
            cart_revision=cart.revision,
            subtotal_toman=quote.subtotal_toman,
            discount_toman=quote.discount_toman,
            shipping_toman=quote.shipping_toman,
            tax_toman=quote.tax_toman,
            payable_toman=quote.payable_toman,
            tax_rate_bps=quote.tax_rate_bps,
            address_snapshot=address_snapshot(address),
            shipping_snapshot=shipping_snapshot(method),
            expires_at=expires_at,
        )

        for priced_line in sorted(priced_lines, key=lambda item: str(item.line.variant_id)):
            line = priced_line.line
            try:
                reservation = reserve_variant(
                    UUID(str(line.variant_id)),
                    quantity=line.quantity,
                    ttl=DEFAULT_RESERVATION_TTL,
                    at=now,
                )
            except (InventoryUnavailableError, VariantInventory.DoesNotExist) as exc:
                raise CheckoutUnavailableError(
                    "Authoritative inventory cannot satisfy this checkout."
                ) from exc

            CheckoutLine.objects.create(
                checkout=checkout,
                variant_id=line.variant_id,
                reservation=reservation,
                quantity=line.quantity,
                unit_price_toman=priced_line.unit_price_toman,
                line_total_toman=priced_line.unit_price_toman * line.quantity,
            )

        return checkout


def get_current_checkout(user: User, *, at: datetime | None = None) -> CheckoutSession | None:
    now = at or timezone.now()
    with transaction.atomic():
        User.objects.select_for_update().only("pk").get(pk=user.pk)
        session = (
            CheckoutSession.objects.select_for_update()
            .filter(
                user=user,
                status__in=(CheckoutSession.Status.ACTIVE, CheckoutSession.Status.READY),
            )
            .order_by("-created_at", "id")
            .first()
        )
        if session is None:
            return None
        if session.expires_at <= now:
            _terminate_session(session, status=CheckoutSession.Status.EXPIRED, at=now)
            return None
        return session


def cancel_checkout(
    user: User,
    checkout_id: UUID,
    *,
    at: datetime | None = None,
) -> CheckoutSession:
    now = at or timezone.now()
    with transaction.atomic():
        User.objects.select_for_update().only("pk").get(pk=user.pk)
        try:
            session = CheckoutSession.objects.select_for_update().get(pk=checkout_id, user=user)
        except CheckoutSession.DoesNotExist as exc:
            raise CheckoutNotFoundError("Checkout session does not exist for this user.") from exc
        if session.status == CheckoutSession.Status.COMPLETED:
            raise CheckoutConflictError("Completed checkout cannot be cancelled.")
        return _terminate_session(session, status=CheckoutSession.Status.CANCELLED, at=now)


def _session_line_map(session: CheckoutSession) -> dict[UUID, CheckoutLine]:
    lines = CheckoutLine.objects.select_for_update().filter(checkout=session).order_by("variant_id")
    return {UUID(str(line.variant_id)): line for line in lines}


def _revalidate_ready_boundary(
    user: User,
    session: CheckoutSession,
    *,
    at: datetime,
) -> None:
    if session.expires_at <= at:
        _terminate_session(session, status=CheckoutSession.Status.EXPIRED, at=at)
        raise CheckoutStaleError("Checkout reservations have expired.")

    try:
        cart = Cart.objects.select_for_update().get(pk=session.cart_id, user=user, status=Cart.Status.ACTIVE)
    except Cart.DoesNotExist as exc:
        raise CheckoutStaleError("Checkout cart is no longer active.") from exc
    if cart.revision != session.cart_revision:
        raise CheckoutStaleError("Cart changed after checkout validation.")

    address = _owned_address(user, session.address_id, lock=True)
    if address_snapshot(address) != session.address_snapshot:
        raise CheckoutStaleError("Shipping address changed after checkout validation.")

    zone = _resolve_zone(address, lock=True)
    method = _method_for_zone(zone, session.shipping_method.code, lock=True)
    if method.pk != session.shipping_method_id or shipping_snapshot(method) != session.shipping_snapshot:
        raise CheckoutStaleError("Shipping configuration changed after checkout validation.")

    tax_policy = _active_tax_policy(address.country_code, lock=True)
    cart_locked, priced_lines, subtotal = _locked_cart_and_prices(user)
    if cart_locked.pk != cart.pk or cart_locked.revision != session.cart_revision:
        raise CheckoutStaleError("Cart changed after checkout validation.")

    checkout_lines = _session_line_map(session)
    current_variant_ids = {UUID(str(item.line.variant_id)) for item in priced_lines}
    if current_variant_ids != set(checkout_lines):
        raise CheckoutStaleError("Cart lines changed after checkout validation.")

    for priced_line in priced_lines:
        variant_id = UUID(str(priced_line.line.variant_id))
        checkout_line = checkout_lines[variant_id]
        if checkout_line.quantity != priced_line.line.quantity:
            raise CheckoutStaleError("Cart quantities changed after checkout validation.")
        if int(checkout_line.unit_price_toman) != priced_line.unit_price_toman:
            raise CheckoutStaleError("Price changed after checkout validation.")
        if int(checkout_line.line_total_toman) != priced_line.unit_price_toman * priced_line.line.quantity:
            raise CheckoutStaleError("Checkout line total is stale.")

    inventory_rows = list(
        VariantInventory.objects.select_for_update()
        .filter(variant_id__in=current_variant_ids)
        .order_by("variant_id")
    )
    inventory_by_variant = {UUID(str(item.variant_id)): item for item in inventory_rows}
    reservation_ids = [line.reservation_id for line in checkout_lines.values()]
    reservations = list(
        InventoryReservation.objects.select_for_update()
        .filter(pk__in=reservation_ids)
        .order_by("inventory_id", "id")
    )
    reservation_by_id = {item.pk: item for item in reservations}

    for variant_id, checkout_line in checkout_lines.items():
        inventory = inventory_by_variant.get(variant_id)
        reservation = reservation_by_id.get(checkout_line.reservation_id)
        if inventory is None or not inventory.is_active:
            raise CheckoutStaleError("Inventory authority is no longer active.")
        if reservation is None:
            raise CheckoutStaleError("Checkout reservation is missing.")
        if reservation.status != InventoryReservation.Status.ACTIVE or reservation.expires_at <= at:
            raise CheckoutStaleError("Checkout reservation is no longer active.")
        if reservation.quantity != checkout_line.quantity:
            raise CheckoutStaleError("Checkout reservation quantity is inconsistent.")

    quote = _quote(method, subtotal_toman=subtotal, policy=tax_policy)
    stored = (
        int(session.subtotal_toman),
        int(session.discount_toman),
        int(session.shipping_toman),
        int(session.tax_toman),
        int(session.payable_toman),
        session.tax_rate_bps,
    )
    current = (
        quote.subtotal_toman,
        quote.discount_toman,
        quote.shipping_toman,
        quote.tax_toman,
        quote.payable_toman,
        quote.tax_rate_bps,
    )
    if stored != current:
        raise CheckoutStaleError("Authoritative checkout totals changed after validation.")


def finalize_checkout(
    user: User,
    checkout_id: UUID,
    *,
    idempotency_key: UUID,
    at: datetime | None = None,
) -> CheckoutSession:
    now = at or timezone.now()
    with transaction.atomic():
        User.objects.select_for_update().only("pk").get(pk=user.pk)
        try:
            session = (
                CheckoutSession.objects.select_for_update()
                .select_related("shipping_method", "shipping_method__zone")
                .get(pk=checkout_id, user=user)
            )
        except CheckoutSession.DoesNotExist as exc:
            raise CheckoutNotFoundError("Checkout session does not exist for this user.") from exc

        if session.status == CheckoutSession.Status.READY:
            if session.expires_at <= now:
                _terminate_session(session, status=CheckoutSession.Status.EXPIRED, at=now)
                raise CheckoutStaleError("Checkout reservations have expired.")
            if session.finalization_key == idempotency_key:
                return session
            raise CheckoutConflictError("Checkout was already finalized with a different key.")
        if session.status != CheckoutSession.Status.ACTIVE:
            raise CheckoutConflictError(f"Checkout in state {session.status!r} cannot be finalized.")

        _revalidate_ready_boundary(user, session, at=now)
        session.status = CheckoutSession.Status.READY
        session.finalization_key = idempotency_key
        session.finalized_at = now
        session.updated_at = now
        session.save(
            update_fields=("status", "finalization_key", "finalized_at", "updated_at")
        )
        return session
