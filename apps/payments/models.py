from __future__ import annotations

from uuid import uuid4

from django.db import models
from django.utils import timezone

from apps.orders.models import Order

PROVIDER_ZARINPAL = "zarinpal"
CURRENCY_CODE = "IRR"
DISPLAY_UNIT = "تومان"


class PaymentAttempt(models.Model):
    class Provider(models.TextChoices):
        ZARINPAL = PROVIDER_ZARINPAL, "ZarinPal"

    class Status(models.TextChoices):
        NEW = "new", "New"
        REQUESTING = "requesting", "Requesting"
        PENDING = "pending", "Pending"
        VERIFYING = "verifying", "Verifying"
        VERIFIED = "verified", "Verified"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        EXPIRED = "expired", "Expired"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payment_attempts")
    idempotency_key = models.UUIDField()
    provider = models.CharField(max_length=24, choices=Provider.choices)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.NEW)
    amount_toman = models.DecimalField(max_digits=18, decimal_places=0)
    amount_rial = models.DecimalField(max_digits=19, decimal_places=0)
    currency_code = models.CharField(max_length=3, default=CURRENCY_CODE)
    display_unit = models.CharField(max_length=16, default=DISPLAY_UNIT)
    provider_authority = models.CharField(max_length=64, blank=True, default="")
    provider_redirect_url = models.CharField(max_length=500, blank=True, default="")
    provider_ref_id = models.CharField(max_length=128, blank=True, default="")
    provider_code = models.IntegerField(null=True, blank=True)
    provider_message = models.CharField(max_length=500, blank=True, default="")
    masked_card = models.CharField(max_length=32, blank=True, default="")
    card_hash = models.CharField(max_length=128, blank=True, default="")
    last_callback_status = models.CharField(max_length=32, blank=True, default="")
    request_count = models.PositiveIntegerField(default=0)
    callback_count = models.PositiveIntegerField(default=0)
    verify_count = models.PositiveIntegerField(default=0)
    verified_at = models.DateTimeField(null=True, blank=True)
    status_changed_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("order", "idempotency_key"),
                name="payments_order_request_key_unique",
            ),
            models.UniqueConstraint(
                fields=("provider", "provider_authority"),
                condition=~models.Q(provider_authority=""),
                name="payments_provider_authority_unique",
            ),
            models.CheckConstraint(
                condition=models.Q(amount_toman__gte=0),
                name="payments_amount_toman_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(amount_rial=models.F("amount_toman") * 10),
                name="payments_rial_toman_exact",
            ),
            models.CheckConstraint(
                condition=models.Q(currency_code=CURRENCY_CODE),
                name="payments_currency_irr",
            ),
            models.CheckConstraint(
                condition=models.Q(display_unit=DISPLAY_UNIT),
                name="payments_display_unit_toman",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.order_id}: {self.provider} / {self.status}"


class PaymentReconciliation(models.Model):
    class Status(models.TextChoices):
        MATCHED = "matched", "Matched"
        MISMATCH = "mismatch", "Mismatch"
        PROVIDER_ERROR = "provider_error", "Provider error"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    attempt = models.ForeignKey(
        PaymentAttempt,
        on_delete=models.CASCADE,
        related_name="reconciliations",
    )
    status = models.CharField(max_length=24, choices=Status.choices)
    provider_code = models.IntegerField(null=True, blank=True)
    provider_ref_id = models.CharField(max_length=128, blank=True, default="")
    provider_payload_digest = models.CharField(max_length=64)
    detail = models.CharField(max_length=500, blank=True, default="")
    checked_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("-checked_at", "id")

    def __str__(self) -> str:
        return f"{self.attempt_id}: {self.status}"
