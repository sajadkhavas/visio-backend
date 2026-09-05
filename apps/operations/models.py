from __future__ import annotations

from uuid import uuid4

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class AuditChainState(models.Model):
    """Single-row serialization point for the tamper-evident audit chain."""

    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    last_sequence = models.PositiveBigIntegerField(default=0)
    last_hash = models.CharField(max_length=64, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "audit chain state"
        verbose_name_plural = "audit chain state"

    def __str__(self) -> str:
        return f"audit-chain:{self.last_sequence}"


class AuditEvent(models.Model):
    """Append-only, hash-chained evidence for security and operational mutations."""

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    sequence = models.PositiveBigIntegerField(unique=True, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="operational_audit_events",
    )
    actor_email_snapshot = models.EmailField(blank=True, default="")
    action = models.CharField(max_length=100)
    object_type = models.CharField(max_length=100)
    object_id = models.CharField(max_length=100)
    summary = models.CharField(max_length=500)
    metadata = models.JSONField(default=dict, blank=True)
    previous_hash = models.CharField(max_length=64, blank=True, default="")
    event_hash = models.CharField(max_length=64, unique=True, editable=False)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ("sequence",)
        indexes = [
            models.Index(fields=("object_type", "object_id", "sequence"), name="ops_audit_object_idx"),
            models.Index(fields=("action", "sequence"), name="ops_audit_action_idx"),
        ]
        constraints = [
            models.CheckConstraint(condition=models.Q(sequence__gt=0), name="ops_audit_sequence_positive"),
            models.CheckConstraint(condition=~models.Q(event_hash=""), name="ops_audit_hash_nonempty"),
        ]
        permissions = [
            ("verify_audit_chain", "Can verify the operational audit chain"),
        ]

    def save(self, *args: object, **kwargs: object) -> None:
        if not self._state.adding:
            raise ValidationError("Audit events are append-only and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> tuple[int, dict[str, int]]:
        raise ValidationError("Audit events are append-only and cannot be deleted.")

    def __str__(self) -> str:
        return f"#{self.sequence} {self.action} {self.object_type}:{self.object_id}"


class NotificationOutbox(models.Model):
    class Channel(models.TextChoices):
        EMAIL = "email", "Email"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        SENDING = "sending", "Sending"
        SENT = "sent", "Sent"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    dedupe_key = models.CharField(max_length=200, unique=True)
    event_type = models.CharField(max_length=64)
    channel = models.CharField(max_length=16, choices=Channel.choices, default=Channel.EMAIL)
    recipient = models.EmailField()
    subject = models.CharField(max_length=255)
    body = models.TextField()
    payload = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempt_count = models.PositiveIntegerField(default=0)
    available_at = models.DateTimeField(default=timezone.now)
    sent_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("created_at", "id")
        indexes = [
            models.Index(fields=("status", "available_at", "created_at"), name="ops_notify_ready_idx"),
            models.Index(fields=("event_type", "created_at"), name="ops_notify_event_idx"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(status=Status.SENT) | models.Q(sent_at__isnull=False),
                name="ops_notify_sent_has_timestamp",
            ),
        ]
        permissions = [
            ("dispatch_notificationoutbox", "Can dispatch notification outbox entries"),
        ]

    def __str__(self) -> str:
        return f"{self.event_type} -> {self.recipient} ({self.status})"


class NotificationDeliveryAttempt(models.Model):
    class Result(models.TextChoices):
        SUCCESS = "success", "Success"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    notification = models.ForeignKey(
        NotificationOutbox,
        on_delete=models.CASCADE,
        related_name="delivery_attempts",
    )
    attempt_no = models.PositiveIntegerField()
    result = models.CharField(max_length=16, choices=Result.choices)
    error = models.CharField(max_length=500, blank=True, default="")
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        ordering = ("notification_id", "attempt_no")
        constraints = [
            models.UniqueConstraint(
                fields=("notification", "attempt_no"),
                name="ops_notify_attempt_unique",
            ),
            models.CheckConstraint(condition=models.Q(attempt_no__gt=0), name="ops_notify_attempt_positive"),
        ]

    def save(self, *args: object, **kwargs: object) -> None:
        if not self._state.adding:
            raise ValidationError("Notification delivery attempts are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args: object, **kwargs: object) -> tuple[int, dict[str, int]]:
        raise ValidationError("Notification delivery attempts are append-only.")

    def __str__(self) -> str:
        return f"{self.notification_id} attempt {self.attempt_no}: {self.result}"
