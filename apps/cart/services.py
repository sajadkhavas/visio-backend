from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone

from apps.accounts.models import User
from apps.catalog.models import Product, ProductVariant
from apps.commerce.projections import variant_availability_payload

from .models import CART_MAX_QUANTITY, Cart, CartLine, WishlistItem

MAX_IMPORT_LINES = 100


class CartNotFoundError(Exception):
    """Raised when a user has no active cart."""


class CartLineNotFoundError(Exception):
    """Raised when a variant is not present in the user's active cart."""


class VariantNotPurchasableError(Exception):
    """Raised when a requested variant is not currently public/purchasable."""


class WishlistProductUnavailableError(Exception):
    """Raised when a product is not currently public for wishlist insertion."""


@dataclass(frozen=True)
class BrowserCartLine:
    variant_id: UUID
    quantity: int


@dataclass(frozen=True)
class ImportIssue:
    variant_id: UUID
    code: str


def validate_quantity(quantity: int) -> int:
    if quantity < 1 or quantity > CART_MAX_QUANTITY:
        raise ValueError(f"Cart quantity must be between 1 and {CART_MAX_QUANTITY}.")
    return quantity


def _purchasable_variant(variant_id: UUID) -> ProductVariant:
    try:
        return ProductVariant.objects.select_related("product").get(
            pk=variant_id,
            is_active=True,
            product__status=Product.Status.PUBLISHED,
        )
    except ProductVariant.DoesNotExist as exc:
        raise VariantNotPurchasableError("Variant is not currently purchasable.") from exc


def get_active_cart(user: User) -> Cart | None:
    return Cart.objects.filter(user=user, status=Cart.Status.ACTIVE).first()


def get_or_create_active_cart(user: User) -> Cart:
    current = get_active_cart(user)
    if current is not None:
        return current

    try:
        with transaction.atomic():
            return Cart.objects.create(user=user, status=Cart.Status.ACTIVE)
    except IntegrityError:
        return Cart.objects.get(user=user, status=Cart.Status.ACTIVE)


def _touch_cart(cart: Cart) -> None:
    now = timezone.now()
    Cart.objects.filter(pk=cart.pk).update(
        revision=F("revision") + 1,
        updated_at=now,
    )
    cart.refresh_from_db(fields=("revision", "updated_at"))


def add_cart_line(user: User, variant_id: UUID, *, quantity: int) -> Cart:
    validate_quantity(quantity)
    variant = _purchasable_variant(variant_id)
    cart = get_or_create_active_cart(user)

    with transaction.atomic():
        locked_cart = Cart.objects.select_for_update().get(pk=cart.pk)
        line = (
            CartLine.objects.select_for_update().filter(cart=locked_cart, variant=variant).first()
        )
        if line is None:
            CartLine.objects.create(cart=locked_cart, variant=variant, quantity=quantity)
        else:
            line.quantity = min(CART_MAX_QUANTITY, line.quantity + quantity)
            line.save(update_fields=("quantity", "updated_at"))
        _touch_cart(locked_cart)
        return locked_cart


def set_cart_line_quantity(
    user: User,
    variant_id: UUID,
    *,
    quantity: int,
) -> Cart:
    validate_quantity(quantity)
    cart = get_active_cart(user)
    if cart is None:
        raise CartNotFoundError("Active cart does not exist.")

    with transaction.atomic():
        locked_cart = Cart.objects.select_for_update().get(pk=cart.pk)
        line = (
            CartLine.objects.select_for_update()
            .filter(cart=locked_cart, variant_id=variant_id)
            .first()
        )
        if line is None:
            raise CartLineNotFoundError("Cart line does not exist.")
        line.quantity = quantity
        line.save(update_fields=("quantity", "updated_at"))
        _touch_cart(locked_cart)
        return locked_cart


def remove_cart_line(user: User, variant_id: UUID) -> Cart:
    cart = get_active_cart(user)
    if cart is None:
        raise CartNotFoundError("Active cart does not exist.")

    with transaction.atomic():
        locked_cart = Cart.objects.select_for_update().get(pk=cart.pk)
        deleted, _details = CartLine.objects.filter(
            cart=locked_cart,
            variant_id=variant_id,
        ).delete()
        if deleted == 0:
            raise CartLineNotFoundError("Cart line does not exist.")
        _touch_cart(locked_cart)
        return locked_cart


def clear_cart(user: User) -> Cart:
    cart = get_or_create_active_cart(user)
    with transaction.atomic():
        locked_cart = Cart.objects.select_for_update().get(pk=cart.pk)
        deleted, _details = CartLine.objects.filter(cart=locked_cart).delete()
        if deleted:
            _touch_cart(locked_cart)
        return locked_cart


def validate_and_clamp_cart(user: User) -> tuple[Cart, list[tuple[UUID, int]]]:
    cart = get_or_create_active_cart(user)
    adjusted: list[tuple[UUID, int]] = []
    now = timezone.now()

    with transaction.atomic():
        locked_cart = Cart.objects.select_for_update().get(pk=cart.pk)
        lines = list(
            CartLine.objects.select_for_update()
            .filter(cart=locked_cart)
            .select_related("variant", "variant__product")
        )
        changed = False
        for line in lines:
            variant = line.variant
            if not variant.is_active or variant.product.status != Product.Status.PUBLISHED:
                continue
            availability = variant_availability_payload(variant, at=now)
            if not availability["authoritative"]:
                continue
            maximum = availability["maxQuantity"]
            if not isinstance(maximum, int) or maximum < 1 or line.quantity <= maximum:
                continue
            line.quantity = min(maximum, CART_MAX_QUANTITY)
            line.save(update_fields=("quantity", "updated_at"))
            adjusted.append((variant.id, line.quantity))
            changed = True

        if changed:
            _touch_cart(locked_cart)
        return locked_cart, adjusted


def merge_browser_cart(
    user: User,
    lines: Iterable[BrowserCartLine],
) -> tuple[Cart, list[ImportIssue]]:
    raw_lines = list(lines)
    if len(raw_lines) > MAX_IMPORT_LINES:
        raise ValueError(f"Import payload cannot exceed {MAX_IMPORT_LINES} lines.")

    deduplicated: dict[UUID, int] = {}
    for raw_line in raw_lines:
        validate_quantity(raw_line.quantity)
        deduplicated[raw_line.variant_id] = min(
            CART_MAX_QUANTITY,
            deduplicated.get(raw_line.variant_id, 0) + raw_line.quantity,
        )

    accepted: dict[UUID, tuple[ProductVariant, int]] = {}
    issues: list[ImportIssue] = []
    for variant_id in sorted(deduplicated, key=str):
        try:
            variant = _purchasable_variant(variant_id)
        except VariantNotPurchasableError:
            issues.append(ImportIssue(variant_id=variant_id, code="variant-unavailable"))
            continue
        accepted[variant_id] = (variant, deduplicated[variant_id])

    cart = get_or_create_active_cart(user)
    with transaction.atomic():
        locked_cart = Cart.objects.select_for_update().get(pk=cart.pk)
        changed = False
        for variant_id in sorted(accepted, key=str):
            variant, imported_quantity = accepted[variant_id]
            cart_line = (
                CartLine.objects.select_for_update()
                .filter(cart=locked_cart, variant=variant)
                .first()
            )
            if cart_line is None:
                CartLine.objects.create(
                    cart=locked_cart,
                    variant=variant,
                    quantity=imported_quantity,
                )
                changed = True
                continue

            merged_quantity = max(cart_line.quantity, imported_quantity)
            if merged_quantity != cart_line.quantity:
                cart_line.quantity = merged_quantity
                cart_line.save(update_fields=("quantity", "updated_at"))
                changed = True

        if changed:
            _touch_cart(locked_cart)
        return locked_cart, issues


def add_wishlist_product(user: User, product_id: UUID) -> None:
    try:
        product = Product.objects.get(pk=product_id, status=Product.Status.PUBLISHED)
    except Product.DoesNotExist as exc:
        raise WishlistProductUnavailableError("Product is not currently public.") from exc
    WishlistItem.objects.get_or_create(user=user, product=product)


def remove_wishlist_product(user: User, product_id: UUID) -> None:
    WishlistItem.objects.filter(user=user, product_id=product_id).delete()
