from __future__ import annotations

from uuid import uuid4

from django.db import models

from apps.catalog.models import ProductVariant


class VariantPrice(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    variant = models.OneToOneField(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="price_record",
    )
    amount_toman = models.DecimalField(max_digits=18, decimal_places=0)
    compare_at_toman = models.DecimalField(
        max_digits=18,
        decimal_places=0,
        null=True,
        blank=True,
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("variant_id",)
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_toman__gte=0),
                name="commerce_price_amount_nonnegative",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(compare_at_toman__isnull=True)
                    | models.Q(compare_at_toman__gt=models.F("amount_toman"))
                ),
                name="commerce_compare_at_gt_amount",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.variant_id}: {self.amount_toman} toman"


class VariantInventory(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    variant = models.OneToOneField(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="inventory_record",
    )
    on_hand = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("variant_id",)

    def __str__(self) -> str:
        return f"{self.variant_id}: on_hand={self.on_hand}"


class InventoryReservation(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        RELEASED = "released", "Released"
        CONSUMED = "consumed", "Consumed"
        EXPIRED = "expired", "Expired"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    inventory = models.ForeignKey(
        VariantInventory,
        on_delete=models.CASCADE,
        related_name="reservations",
    )
    quantity = models.PositiveIntegerField()
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at", "id")
        indexes = [
            models.Index(
                fields=("inventory", "status", "expires_at"),
                name="commerce_res_active_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="commerce_res_quantity_positive",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.inventory_id}: {self.quantity} ({self.status})"
