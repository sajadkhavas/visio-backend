from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db.models import F, Q

from apps.orders.models import Order
from apps.payments.models import PaymentAttempt, PaymentReconciliation

from ...audit import verify_audit_chain


class Command(BaseCommand):
    help = "Verify cross-domain business and audit invariants without mutating production data."

    def handle(self, *args: object, **options: object) -> None:
        del args, options
        failures: list[str] = []

        audit_ok, audit_detail = verify_audit_chain()
        if not audit_ok:
            failures.append(f"audit chain: {audit_detail}")

        verified_missing_evidence = PaymentAttempt.objects.filter(
            status=PaymentAttempt.Status.VERIFIED
        ).filter(Q(verified_at__isnull=True) | Q(provider_ref_id=""))
        if verified_missing_evidence.exists():
            failures.append("verified payment attempts are missing provider verification evidence")

        nonverified_with_verified_at = PaymentAttempt.objects.exclude(
            status=PaymentAttempt.Status.VERIFIED
        ).filter(verified_at__isnull=False)
        if nonverified_with_verified_at.exists():
            failures.append("non-verified payment attempts unexpectedly have verified_at")

        amount_mismatches = PaymentAttempt.objects.exclude(amount_rial=F("amount_toman") * 10)
        if amount_mismatches.exists():
            failures.append("payment rial/toman conversion mismatch detected")

        post_payment_statuses = (
            Order.Status.CONFIRMED,
            Order.Status.PROCESSING,
            Order.Status.SHIPPED,
            Order.Status.DELIVERED,
        )
        orders_without_verified_payment = (
            Order.objects.filter(status__in=post_payment_statuses)
            .exclude(payment_attempts__status=PaymentAttempt.Status.VERIFIED)
            .distinct()
        )
        if orders_without_verified_payment.exists():
            failures.append("post-payment orders exist without a verified payment attempt")

        verified_without_reconciliation = PaymentAttempt.objects.filter(
            status=PaymentAttempt.Status.VERIFIED,
            reconciliations__isnull=True,
        )
        if verified_without_reconciliation.exists():
            failures.append("verified payment attempts exist without reconciliation evidence")

        matched_on_unverified = PaymentReconciliation.objects.filter(
            status=PaymentReconciliation.Status.MATCHED
        ).exclude(attempt__status=PaymentAttempt.Status.VERIFIED)
        if matched_on_unverified.exists():
            failures.append("matched reconciliation exists for a non-verified payment attempt")

        if failures:
            raise CommandError("Business integrity verification failed: " + "; ".join(failures))

        self.stdout.write(
            self.style.SUCCESS(
                "Business integrity verification passed: audit/payment/order/reconciliation "
                "truth is consistent."
            )
        )
