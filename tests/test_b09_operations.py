from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest
from django.contrib import admin
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import Client, RequestFactory

from apps.accounts.admin import VisioUserAdmin
from apps.accounts.models import User
from apps.commerce.models import InventoryReservation
from apps.commerce.services import InventoryUnavailableError
from apps.operations.audit import append_audit_event, verify_audit_chain
from apps.operations.models import AuditEvent, NotificationDeliveryAttempt, NotificationOutbox
from apps.operations.notifications import NotificationOutbox as NotificationModel
from apps.operations.notifications import dispatch_notification, queue_notification
from apps.operations.roles import ROLE_MATRIX, sync_staff_roles
from apps.operations.staff_services import (
    advance_order_as_staff,
    set_inventory_as_staff,
)
from apps.orders.models import Order
from apps.payments.services import reconcile_attempt, start_payment
from tests.test_b07_payments import FakeProvider, authenticated_client, prepare_pending_order

pytestmark = pytest.mark.django_db(transaction=True)


class FailingSender:
    def send(self, notification: NotificationOutbox) -> None:
        raise RuntimeError("delivery unavailable")


class SuccessfulSender:
    def __init__(self) -> None:
        self.sent_ids: list[str] = []

    def send(self, notification: NotificationOutbox) -> None:
        self.sent_ids.append(str(notification.id))


def permission(app_label: str, codename: str) -> Permission:
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def staff_user(email: str, *permissions: Permission) -> User:
    user = User.objects.create_user(
        username=email,
        email=email,
        password="Correct-Horse-Battery-55",
        is_staff=True,
    )
    if permissions:
        user.user_permissions.add(*permissions)
    return user


def confirmed_order(settings: Any, *, email: str, slug: str) -> tuple[User, Order]:
    customer, order = prepare_pending_order(email=email, slug=slug)
    provider = FakeProvider()
    settings.PAYMENT_CALLBACK_URL = "https://api.example.test/api/v1/payments/zarinpal/callback/"
    attempt = start_payment(
        customer,
        order_public_id=order.public_id,
        idempotency_key=uuid4(),
        provider=provider,
    ).attempt
    outcome = reconcile_attempt(attempt.id, provider=provider)
    assert outcome.order_confirmed is True
    order.refresh_from_db()
    assert order.status == Order.Status.CONFIRMED
    return customer, order


def test_audit_chain_is_append_only_and_detects_database_tampering() -> None:
    actor = staff_user("audit@example.com")
    first = append_audit_event(
        actor=actor,
        action="test.first",
        object_type="tests.Object",
        object_id="one",
        summary="First audit event.",
        metadata={"value": 1},
    )
    second = append_audit_event(
        actor=actor,
        action="test.second",
        object_type="tests.Object",
        object_id="two",
        summary="Second audit event.",
        metadata={"value": 2},
    )

    assert first.sequence == 1
    assert second.sequence == 2
    assert second.previous_hash == first.event_hash
    assert verify_audit_chain() == (True, "ok")

    first.summary = "changed"
    with pytest.raises(ValidationError):
        first.save()
    with pytest.raises(ValidationError):
        first.delete()

    AuditEvent.objects.filter(pk=first.pk).update(summary="tampered outside model API")
    valid, detail = verify_audit_chain()
    assert valid is False
    assert "hash mismatch" in detail


def test_role_matrix_resolves_and_syncs_exact_groups() -> None:
    checked = sync_staff_roles(dry_run=True)
    assert set(checked) == {role.name for role in ROLE_MATRIX}
    assert Group.objects.filter(name__startswith="VISIO ").count() == 0

    synced = sync_staff_roles()
    assert synced == checked
    for role in ROLE_MATRIX:
        group = Group.objects.get(name=role.name)
        actual = {
            (item.content_type.app_label, item.codename)
            for item in group.permissions.select_related("content_type")
        }
        assert actual == set(role.permissions)


def test_operations_summary_requires_explicit_permission() -> None:
    normal = User.objects.create_user(
        username="normal@example.com",
        email="normal@example.com",
        password="Correct-Horse-Battery-55",
    )
    staff_without_perm = staff_user("staff-no-perm@example.com")
    staff_with_perm = staff_user(
        "staff-view@example.com",
        permission("operations", "view_auditevent"),
    )

    assert authenticated_client(normal).get("/api/v1/staff/operations/summary/").status_code == 403
    assert (
        authenticated_client(staff_without_perm).get("/api/v1/staff/operations/summary/").status_code
        == 403
    )
    response = authenticated_client(staff_with_perm).get("/api/v1/staff/operations/summary/")
    assert response.status_code == 200
    assert set(response.json()) == {
        "orders",
        "paymentReconciliationMismatches",
        "notifications",
        "auditEvents",
    }


def test_staff_order_transition_uses_domain_service_audit_and_notification(settings: Any) -> None:
    _, order = confirmed_order(
        settings,
        email="staff-order@example.com",
        slug="staff-order",
    )
    actor = staff_user(
        "fulfillment@example.com",
        permission("orders", "change_order"),
    )
    NotificationOutbox.objects.all().delete()

    result = advance_order_as_staff(
        actor,
        order_id=order.id,
        target_status=Order.Status.PROCESSING,
    )

    assert result.status == Order.Status.PROCESSING
    assert AuditEvent.objects.filter(
        actor=actor,
        action="order.fulfillment_advanced",
        object_id=str(order.id),
    ).exists()
    queued = NotificationOutbox.objects.get(
        dedupe_key=f"order:{order.id}:status:{Order.Status.PROCESSING}"
    )
    assert queued.status == NotificationOutbox.Status.PENDING
    assert queued.recipient == "staff-order@example.com"


def test_unauthorized_staff_cannot_advance_order(settings: Any) -> None:
    _, order = confirmed_order(
        settings,
        email="unauthorized-order@example.com",
        slug="unauthorized-order",
    )
    actor = staff_user("unauthorized-staff@example.com")
    AuditEvent.objects.all().delete()

    with pytest.raises(PermissionDenied):
        advance_order_as_staff(
            actor,
            order_id=order.id,
            target_status=Order.Status.PROCESSING,
        )

    order.refresh_from_db()
    assert order.status == Order.Status.CONFIRMED
    assert AuditEvent.objects.count() == 0


def test_staff_inventory_mutation_preserves_active_reservation_invariant(settings: Any) -> None:
    _, order = prepare_pending_order(
        email="inventory-staff@example.com",
        slug="inventory-staff",
    )
    reservation = InventoryReservation.objects.select_related("inventory").get(order_line__order=order)
    actor = staff_user(
        "catalog-ops@example.com",
        permission("commerce", "change_variantinventory"),
    )

    with pytest.raises(InventoryUnavailableError):
        set_inventory_as_staff(
            actor,
            variant_id=reservation.inventory.variant_id,
            on_hand=0,
            is_active=True,
        )
    assert not AuditEvent.objects.filter(action="inventory.updated").exists()

    inventory = set_inventory_as_staff(
        actor,
        variant_id=reservation.inventory.variant_id,
        on_hand=4,
        is_active=True,
    )
    assert inventory.on_hand == 4
    assert AuditEvent.objects.filter(action="inventory.updated", actor=actor).count() == 1


def test_notification_failure_is_durable_and_does_not_change_order_truth(settings: Any) -> None:
    _, order = confirmed_order(
        settings,
        email="notify-failure@example.com",
        slug="notify-failure",
    )
    actor = staff_user(
        "notify-operator@example.com",
        permission("orders", "change_order"),
    )
    NotificationOutbox.objects.all().delete()
    result = advance_order_as_staff(
        actor,
        order_id=order.id,
        target_status=Order.Status.PROCESSING,
    )
    notification = NotificationOutbox.objects.get(
        dedupe_key=f"order:{order.id}:status:{Order.Status.PROCESSING}"
    )

    delivery = dispatch_notification(notification.id, sender=FailingSender())

    result.refresh_from_db()
    assert result.status == Order.Status.PROCESSING
    assert delivery.status == NotificationOutbox.Status.FAILED
    assert delivery.attempt_count == 1
    assert "delivery unavailable" in delivery.last_error
    attempt = NotificationDeliveryAttempt.objects.get(notification=delivery)
    assert attempt.result == NotificationDeliveryAttempt.Result.FAILED
    assert AuditEvent.objects.filter(action="order.fulfillment_advanced", actor=actor).exists()


def test_notification_retry_succeeds_without_duplicate_outbox_row() -> None:
    notification = queue_notification(
        dedupe_key="test:dedupe:1",
        event_type="test.event",
        recipient="customer@example.com",
        subject="Subject",
        body="Body",
        payload={"value": 1},
    )
    replay = queue_notification(
        dedupe_key="test:dedupe:1",
        event_type="test.event",
        recipient="customer@example.com",
        subject="Subject",
        body="Body",
        payload={"value": 1},
    )
    assert replay.id == notification.id
    assert NotificationOutbox.objects.filter(dedupe_key="test:dedupe:1").count() == 1

    failed = dispatch_notification(notification.id, sender=FailingSender())
    sender = SuccessfulSender()
    sent = dispatch_notification(failed.id, sender=sender)

    assert sent.status == NotificationOutbox.Status.SENT
    assert sent.attempt_count == 2
    assert sent.sent_at is not None
    assert sender.sent_ids == [str(notification.id)]
    assert NotificationDeliveryAttempt.objects.filter(notification=sent).count() == 2


def test_payment_and_order_confirmation_notifications_are_deduplicated(settings: Any) -> None:
    _, order = confirmed_order(
        settings,
        email="payment-notification@example.com",
        slug="payment-notification",
    )

    assert NotificationOutbox.objects.filter(
        dedupe_key=f"order:{order.id}:status:{Order.Status.CONFIRMED}"
    ).count() == 1
    payment_notification = NotificationOutbox.objects.get(event_type="payment.verified")
    assert payment_notification.recipient == "payment-notification@example.com"


def test_non_superuser_admin_cannot_escalate_role_fields() -> None:
    request = RequestFactory().get("/admin/accounts/user/")
    request.user = staff_user("support-admin@example.com", permission("accounts", "change_user"))
    model_admin = VisioUserAdmin(User, admin.site)
    target = User.objects.create_user(
        username="target@example.com",
        email="target@example.com",
        password="Correct-Horse-Battery-55",
    )

    readonly = set(model_admin.get_readonly_fields(request, target))
    assert {"is_staff", "is_superuser", "groups", "user_permissions"}.issubset(readonly)
