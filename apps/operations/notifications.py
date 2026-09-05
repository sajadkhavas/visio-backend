from __future__ import annotations

from functools import partial
from typing import Any, Protocol
from uuid import UUID

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.utils import timezone

from .models import NotificationDeliveryAttempt, NotificationOutbox


class NotificationError(Exception):
    pass


class NotificationConfigurationError(NotificationError):
    pass


class NotificationConflictError(NotificationError):
    pass


class NotificationSender(Protocol):
    def send(self, notification: NotificationOutbox) -> None: ...


class DjangoEmailSender:
    def send(self, notification: NotificationOutbox) -> None:
        if notification.channel != NotificationOutbox.Channel.EMAIL:
            raise NotificationConfigurationError("DjangoEmailSender only supports email notifications.")
        sent = EmailMessage(
            subject=notification.subject,
            body=notification.body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[notification.recipient],
        ).send(fail_silently=False)
        if sent != 1:
            raise NotificationError("Email backend did not report a successful delivery.")


def _sender_from_settings() -> NotificationSender:
    if not settings.NOTIFICATIONS_ENABLED:
        raise NotificationConfigurationError("Notifications are disabled.")
    if settings.NOTIFICATION_CHANNEL != NotificationOutbox.Channel.EMAIL:
        raise NotificationConfigurationError("Configured notification channel is unsupported.")
    return DjangoEmailSender()


def _validate_header_value(value: str, *, name: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"Notification {name} is required.")
    if "\r" in cleaned or "\n" in cleaned:
        raise ValueError(f"Notification {name} cannot contain line breaks.")
    return cleaned


def queue_notification(
    *,
    dedupe_key: str,
    event_type: str,
    recipient: str,
    subject: str,
    body: str,
    payload: dict[str, Any] | None = None,
) -> NotificationOutbox:
    key = _validate_header_value(dedupe_key, name="dedupe key")
    event = _validate_header_value(event_type, name="event type")
    email = _validate_header_value(recipient, name="recipient")
    subject_value = _validate_header_value(subject, name="subject")
    body_value = body.strip()
    if not body_value:
        raise ValueError("Notification body is required.")

    notification, created = NotificationOutbox.objects.get_or_create(
        dedupe_key=key,
        defaults={
            "event_type": event,
            "channel": NotificationOutbox.Channel.EMAIL,
            "recipient": email,
            "subject": subject_value,
            "body": body_value,
            "payload": dict(payload or {}),
        },
    )
    if not created:
        if (
            notification.event_type != event
            or notification.recipient != email
            or notification.subject != subject_value
            or notification.body != body_value
        ):
            raise NotificationConflictError("Notification dedupe key was reused with different content.")
        return notification

    if settings.NOTIFICATIONS_ENABLED and settings.NOTIFICATIONS_AUTO_DISPATCH:
        transaction.on_commit(partial(dispatch_notification, notification.id), robust=True)
    return notification


def dispatch_notification(
    notification_id: UUID,
    *,
    sender: NotificationSender | None = None,
) -> NotificationOutbox:
    now = timezone.now()
    with transaction.atomic():
        notification = NotificationOutbox.objects.select_for_update().get(pk=notification_id)
        if notification.status == NotificationOutbox.Status.SENT:
            return notification
        if notification.status == NotificationOutbox.Status.SENDING:
            raise NotificationConflictError("Notification delivery is already in progress.")
        if notification.available_at > now:
            raise NotificationConflictError("Notification is not available for delivery yet.")
        notification.status = NotificationOutbox.Status.SENDING
        notification.attempt_count += 1
        notification.last_error = ""
        notification.updated_at = now
        notification.save(
            update_fields=("status", "attempt_count", "last_error", "updated_at")
        )
        attempt_no = notification.attempt_count

    try:
        active_sender = sender if sender is not None else _sender_from_settings()
        active_sender.send(notification)
    except Exception as exc:
        failed_at = timezone.now()
        with transaction.atomic():
            notification = NotificationOutbox.objects.select_for_update().get(pk=notification_id)
            notification.status = NotificationOutbox.Status.FAILED
            notification.last_error = str(exc)[:500]
            notification.updated_at = failed_at
            notification.save(update_fields=("status", "last_error", "updated_at"))
            NotificationDeliveryAttempt.objects.create(
                notification=notification,
                attempt_no=attempt_no,
                result=NotificationDeliveryAttempt.Result.FAILED,
                error=str(exc)[:500],
                created_at=failed_at,
            )
            return notification

    sent_at = timezone.now()
    with transaction.atomic():
        notification = NotificationOutbox.objects.select_for_update().get(pk=notification_id)
        notification.status = NotificationOutbox.Status.SENT
        notification.sent_at = sent_at
        notification.last_error = ""
        notification.updated_at = sent_at
        notification.save(
            update_fields=("status", "sent_at", "last_error", "updated_at")
        )
        NotificationDeliveryAttempt.objects.create(
            notification=notification,
            attempt_no=attempt_no,
            result=NotificationDeliveryAttempt.Result.SUCCESS,
            created_at=sent_at,
        )
        return notification
