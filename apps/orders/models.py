from __future__ import annotations

from uuid import uuid4

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.checkout.models import CheckoutSession
from apps.commerce.models import InventoryReservation

CURRENCY_CODE = "IRR"
DISPLAY_UNIT = "تومان"


class Order(models.Model):
    class Status(models.TextChoices):
        PENDING_PAYMENT = "pending_payment", "Pending payment"
        CONFIRMED = "confirmed", "Confirmed"
        PROCESSING = "processing", "Processing"
        SHIPPED = "shipped", "Shipped"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    public_id = models.UUIDField(default=uuid4, unique=True, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="orders",
    )
    checkout = models.OneToOneField(
        CheckoutSession,
        on_delete=models.PROTECT,
        related_name="order",
    )
    idempotency_key = models.UUIDField()
    status = models.CharField(
        max_length=24,
        choices=Status.choices,
        default=Status.PENDING_PAYMENT,
    )
    status_changed_at = models.DateTimeField(default=timezone.now)
    customer_snapshot = models.JSONField()
    address_snapshot = models.JSONField()
    shipping_snapshot = models.JSONField()
    subtotal_toman = models.DecimalField(max_digits=18, decimal_places=0)
    discount_toman = models.DecimalField(max_digits=18, decimal_places=0, default=0)
    shipping_toman = models.DecimalField(max_digits=18, decimal_places=0)
    tax_toman = models.DecimalField(max_digits=18, decimal_places=0)
    payable_toman = models.DecimalField(max_digits=18, decimal_places=0)
    tax_rate_bps = models.PositiveSmallIntegerField()
    currency_code = models.CharField(max_length=3, default=CURRENCY_CODE)
    display_unit = models.CharField(max_length=16, default=DISPLAY_UNIT)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("user", "idempotency_key"),
                name="orders_user_create_key_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(subtotal_toman__gte=0),
                name="orders_subtotal_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(discount_toman__gte=0),
                name="orders_discount_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(discount_toman__lte=models.F("subtotal_toman")),
                name="orders_discount_within_subtotal",
            ),
            models.CheckConstraint(
                condition=models.Q(shipping_toman__gte=0),
                name="orders_shipping_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(tax_toman__gte=0),
                name="orders_tax_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(payable_toman__gte=0),
                name="orders_payable_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(tax_rate_bps__lte=10_000),
                name="orders_tax_rate_bounded",
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
                name="orders_payable_components",
            ),
            models.CheckConstraint(
                condition=models.Q(currency_code=CURRENCY_CODE),
                name="orders_currency_irr",
            ),
            models.CheckConstraint(
                condition=models.Q(display_unit=DISPLAY_UNIT),
                name="orders_display_unit_toman",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.public_id}: {self.status}"


class OrderLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    reservation = models.OneToOneField(
        InventoryReservation,
        on_delete=models.PROTECT,
        related_name="order_line",
    )
    source_product_id = models.UUIDField()
    source_product_slug = models.CharField(max_length=180)
    source_product_name = models.CharField(max_length=220)
    source_variant_id = models.UUIDField()
    source_variant_sku = models.CharField(max_length=120, blank=True)
    option_snapshot = models.JSONField(default=dict)
    quantity = models.PositiveSmallIntegerField()
    unit_price_toman = models.DecimalField(max_digits=18, decimal_places=0)
    line_total_toman = models.DecimalField(max_digits=18, decimal_places=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("source_variant_id", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("order", "source_variant_id"),
                name="orders_line_variant_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1, quantity__lte=99),
                name="orders_line_quantity_bounded",
            ),
            models.CheckConstraint(
                condition=models.Q(unit_price_toman__gte=0),
                name="orders_line_price_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(line_total_toman__gte=0),
                name="orders_line_total_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    line_total_toman=models.F("unit_price_toman") * models.F("quantity")
                ),
                name="orders_line_total_components",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.order_id}: {self.source_variant_id} x {self.quantity}"
