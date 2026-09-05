from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import HttpRequest

from .models import AuditEvent, NotificationDeliveryAttempt, NotificationOutbox
from .notifications import dispatch_notification


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin[AuditEvent]):
    list_display = (
        "sequence",
        "created_at",
        "actor_email_snapshot",
        "action",
        "object_type",
        "object_id",
    )
    list_filter = ("action", "object_type", "created_at")
    search_fields = ("actor_email_snapshot", "action", "object_type", "object_id", "summary")
    ordering = ("-sequence",)
    readonly_fields = (
        "id",
        "sequence",
        "actor",
        "actor_email_snapshot",
        "action",
        "object_type",
        "object_id",
        "summary",
        "metadata",
        "previous_hash",
        "event_hash",
        "created_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: AuditEvent | None = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: AuditEvent | None = None) -> bool:
        return False


@admin.register(NotificationOutbox)
class NotificationOutboxAdmin(admin.ModelAdmin[NotificationOutbox]):
    list_display = (
        "created_at",
        "event_type",
        "recipient",
        "status",
        "attempt_count",
        "sent_at",
    )
    list_filter = ("status", "event_type", "channel", "created_at")
    search_fields = ("dedupe_key", "recipient", "event_type", "subject")
    ordering = ("-created_at",)
    readonly_fields = (
        "id",
        "dedupe_key",
        "event_type",
        "channel",
        "recipient",
        "subject",
        "body",
        "payload",
        "status",
        "attempt_count",
        "available_at",
        "sent_at",
        "last_error",
        "created_at",
        "updated_at",
    )
    actions = ("retry_delivery",)

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: NotificationOutbox | None = None) -> bool:
        return False

    @admin.action(description="Retry selected pending/failed notifications")
    def retry_delivery(
        self,
        request: HttpRequest,
        queryset: QuerySet[NotificationOutbox],
    ) -> None:
        if not request.user.has_perm("operations.dispatch_notificationoutbox"):
            raise PermissionDenied("Notification dispatch permission is required.")
        sent = 0
        failed = 0
        skipped = 0
        for notification in queryset.order_by("created_at", "id"):
            if notification.status == NotificationOutbox.Status.SENT:
                skipped += 1
                continue
            result = dispatch_notification(notification.id)
            if result.status == NotificationOutbox.Status.SENT:
                sent += 1
            else:
                failed += 1
        self.message_user(
            request,
            f"Notification delivery result: sent={sent}, failed={failed}, skipped={skipped}.",
            level=messages.INFO if failed == 0 else messages.WARNING,
        )


@admin.register(NotificationDeliveryAttempt)
class NotificationDeliveryAttemptAdmin(admin.ModelAdmin[NotificationDeliveryAttempt]):
    list_display = ("created_at", "notification", "attempt_no", "result")
    list_filter = ("result", "created_at")
    search_fields = ("notification__dedupe_key", "notification__recipient", "error")
    ordering = ("-created_at",)
    readonly_fields = (
        "id",
        "notification",
        "attempt_no",
        "result",
        "error",
        "created_at",
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(
        self,
        request: HttpRequest,
        obj: NotificationDeliveryAttempt | None = None,
    ) -> bool:
        return False

    def has_delete_permission(
        self,
        request: HttpRequest,
        obj: NotificationDeliveryAttempt | None = None,
    ) -> bool:
        return False
