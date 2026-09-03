from __future__ import annotations

from uuid import uuid4

from django.conf import settings
from django.db import models

from apps.catalog.models import Product, ProductVariant

CART_MAX_QUANTITY = 99


class Cart(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        CONVERTED = "converted", "Converted"
        ABANDONED = "abandoned", "Abandoned"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="carts",
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    revision = models.PositiveBigIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-updated_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("user",),
                condition=models.Q(status="active"),
                name="cart_one_active_per_user",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}: {self.status}"


class CartLine(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name="lines")
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.PROTECT,
        related_name="cart_lines",
    )
    quantity = models.PositiveSmallIntegerField()
    added_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("added_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("cart", "variant"),
                name="cart_line_variant_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=1, quantity__lte=CART_MAX_QUANTITY),
                name="cart_line_quantity_bounded",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.cart_id}: {self.variant_id} x {self.quantity}"


class WishlistItem(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wishlist_items",
    )
    product = models.ForeignKey(
        Product,
        on_delete=models.PROTECT,
        related_name="wishlist_items",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("user", "product"),
                name="wishlist_user_product_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.user_id}: {self.product_id}"
