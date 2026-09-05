from typing import Any

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpRequest

from apps.accounts.models import User
from apps.operations.audit import append_audit_event

from .models import ContentEntry


def _require_staff_user(request: HttpRequest) -> User:
    actor = request.user
    if not isinstance(actor, User) or not actor.is_staff:
        raise PermissionDenied("Authenticated staff user required for admin mutation.")
    return actor


@admin.register(ContentEntry)
class ContentEntryAdmin(admin.ModelAdmin):
    list_display = ("kind", "slug", "title", "status", "published_at", "updated_at")
    list_filter = ("kind", "status", "published_at")
    search_fields = ("slug", "title", "summary", "search_text")
    ordering = ("kind", "slug")

    def has_delete_permission(self, request: HttpRequest, obj: ContentEntry | None = None) -> bool:
        return False

    def save_model(
        self,
        request: HttpRequest,
        obj: ContentEntry,
        form: Any,
        change: bool,
    ) -> None:
        actor = _require_staff_user(request)
        before_status = None
        if change and obj.pk:
            before_status = ContentEntry.objects.only("status").get(pk=obj.pk).status
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            append_audit_event(
                actor=actor,
                action="content.updated" if change else "content.created",
                object_type="content.ContentEntry",
                object_id=str(obj.pk),
                summary="Editorial content mutation through Django Admin.",
                metadata={
                    "kind": obj.kind,
                    "slug": obj.slug,
                    "fromStatus": before_status,
                    "toStatus": obj.status,
                },
            )
