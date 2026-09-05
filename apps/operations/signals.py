from __future__ import annotations

from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.payments.models import PaymentAttempt

from .notifications import queue_notification


@receiver(post_save, sender=PaymentAttempt, dispatch_uid="operations.payment_verified_notification")
def schedule_verified_payment_notification(
    sender: type[PaymentAttempt],
    instance: PaymentAttempt,
    created: bool,
    **kwargs: object,
) -> None:
    if instance.status != PaymentAttempt.Status.VERIFIED:
        return
    order = instance.order
    recipient = str(order.customer_snapshot.get("email", "")).strip()
    if not recipient:
        return
    queue_notification(
        dedupe_key=f"payment:{instance.id}:verified",
        event_type="payment.verified",
        recipient=recipient,
        subject="پرداخت سفارش شما در VISIO تایید شد",
        body=f"پرداخت سفارش {order.public_id} با موفقیت تایید شد.",
        payload={
            "paymentId": str(instance.id),
            "orderId": str(order.public_id),
            "referenceId": instance.provider_ref_id,
        },
    )
