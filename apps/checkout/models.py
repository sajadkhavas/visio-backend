from __future__ import annotations

from uuid import uuid4

from django.conf import settings
from django.db import models
from django.db.models.functions import Lower

from apps.accounts.models import Address
from apps.cart.models import CART_MAX_QUANTITY, Cart
from apps.catalog.models import ProductVariant
from apps.commerce.models import InventoryReservation

MAX_TAX_RATE_BPS = 10_000


class ShippingZone(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=120)
    country_code = models.CharField(max_length=2)
    province = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("country_code", "province", "city", "code")
        constraints = [
            models.UniqueConstraint(Lower("code"), name="checkout_zone_code_ci_unique"),
            models.UniqueConstraint(
                Lower("country_code"),
                Lower("province"),
                Lower("city"),
                name="checkout_zone_scope_ci_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(city="") | ~models.Q(province=""),
                name="checkout_zone_city_requires_province",
            ),
        ]

    def __str__(self) -> str:
        return self.code


class ShippingMethod(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    zone = models.ForeignKey(ShippingZone, on_delete=models.PROTECT, related_name="methods")
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=120)
    flat_rate_toman = models.DecimalField(max_digits=18, decimal_places=0)
    free_over_toman = models.DecimalField(
        max_digits=18,
        decimal_places=0,
        null=True,
        blank=True,
    )
    delivery_min_days = models.PositiveSmallIntegerField(null=True, blank=True)
    delivery_max_days = models.PositiveSmallIntegerField(null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "code", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("zone", "code"),
                name="checkout_method_zone_code_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(flat_rate_toman__gte=0),
                name="checkout_method_rate_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(free_over_toman__isnull=True) | models.Q(free_over_toman__gte=0)
                ),
                name="checkout_method_free_over_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(delivery_min_days__isnull=True, delivery_max_days__isnull=True)
                    | (
                        models.Q(delivery_min_days__isnull=False)
                        & models.Q(delivery_max_days__isnull=False)
                        & models.Q(delivery_max_days__gte=models.F("delivery_min_days"))
                    )
                ),
                name="checkout_method_delivery_range_valid",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.zone.code}: {self.code}"


class CheckoutTaxPolicy(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    country_code = models.CharField(max_length=2)
    rate_bps = models.PositiveSmallIntegerField()
    applies_to_shipping = models.BooleanField(default=False)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("country_code", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("country_code",),
                condition=models.Q(is_active=True),
                name="checkout_one_active_tax_policy_country",
            ),
            models.CheckConstraint(
                condition=models.Q(rate_bps__lte=MAX_TAX_RATE_BPS),
                name="checkout_tax_rate_bounded",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.country_code}: {self.rate_bps}bps"


class CheckoutSession(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        READY = "ready", "Ready for order"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"
        COMPLETED = "completed", "Completed"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="checkout_sessions",
    )
    cart = models.ForeignKey(Cart, on_delete=models.PROTECT, related_name="checkout_sessions")
    address = models.ForeignKey(
        Address,
        on_delete=models.PROTECT,
        related_name="checkout_sessions",
    )
    shipping_method = models.ForeignKey(
        ShippingMethod,
        on_delete=models.PROTECT,
        related_name="checkout_sessions",
    )
    idempotency_key = models.UUIDField()
    finalization_key = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    cart_revision = models.PositiveBigIntegerField()
    subtotal_toman = models.DecimalField(max_digits=18, decimal_places=0)
    discount_toman = models.DecimalField(max_digits=18, decimal_places=0, default=0)
    shipping_toman = models.DecimalField(max_digits=18, decimal_places=0)
    tax_toman = models.DecimalField(max_digits=18, decimal_places=0)
    payable_toman = models.DecimalField(max_digits=18, decimal_places=0)
    tax_rate_bps = models.PositiveSmallIntegerField()
    address_snapshot = models.JSONField()
    shipping_snapshot = models.JSONField()
    expires_at = models.DateTimeField()
    finalized_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("user", "idempotency_key"),
                name="checkout_user_create_key_unique",
            ),
            models.UniqueConstraint(
                fields=("user", "finalization_key"),
                condition=models.Q(finalization_key__isnull=False),
                name="checkout_user_finalize_key_unique",
            ),
            models.UniqueConstraint(
                fields=("user",),
                condition=models.Q(status__in=("active", "ready")),
                name="checkout_one_nonterminal_per_user",
            ),
            models.CheckConstraint(
                condition=models.Q(subtotal_toman__gte=0),
                name="checkout_subtotal_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(discount_toman__gte=0),
                name="checkout_discount_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(discount_toman__lte=models.F("subtotal_toman")),
                name="checkout_discount_within_subtotal",
            ),
            models.CheckConstraint(
                condition=models.Q(shipping_toman__gte=0),
                name="checkout_shipping_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(tax_toman__gte=0),
                name="checkout_tax_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(payable_toman__gte=0),
                name="checkout_payable_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(tax_rate_bps__lte=MAX_TAX_RATE_BPS),
                name="checkout_session_tax_rate_bounded",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    payable_toman=(
                        models.F("subtotal_toman")
                        - models.F("discount_toman")
                        + models.F("shipping_toman")
                        + models.F("tax_toman")
                    )
                ),
                name="checkout_payable_components",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}: {self.status}"


class CheckoutLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    checkout = models.ForeignKey(
        CheckoutSession,
        on_delete=models.CASCADE,
        related_name="lines",
    )
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="checkout_lines",
    )
    reservation = models.OneToOneField(
        InventoryReservation,
        on_delete=models.PROTECT,
        related_name="checkout_line",
    )
    quantity = models.PositiveSmallIntegerField()
    unit_price_toman = models.DecimalField(max_digits=18, decimal_places=0)
    line_total_toman = models.DecimalField(max_digits=18, decimal_places=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("variant_id", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("checkout", "variant"),
                name="checkout_line_variant_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1, quantity__lte=CART_MAX_QUANTITY),
                name="checkout_line_quantity_bounded",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price_toman__gte=0),
                name="checkout_line_price_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(line_total_toman__gte=0),
                name="checkout_line_total_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    line_total_toman=models.F("unit_price_toman") * models.F("quantity")
                ),
                name="checkout_line_total_components",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.checkout_id}: {self.variant_id} x {self.quantity}"
