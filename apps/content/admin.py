from typing import Any

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import HttpRequest

from apps.accounts.models import User
from apps.operations.audit import append_audit_event

from .models import ContactMessage, ContentEntry, HomepageBlock, SiteConfiguration


def _require_staff_user(request: HttpRequest) -> User:
    actor = request.user
    if not isinstance(actor, User) or not actor.is_staff:
        raise PermissionDenied("Authenticated staff user required for admin mutation.")
    return actor


@admin.register(ContentEntry)
class ContentEntryAdmin(admin.ModelAdmin):
    list_display = ("kind", "slug", "title", "status", "published_at", "updated_at")
    list_filter = ("kind", "status", "published_at")
    search_fields = ("slug", "title", "excerpt", "search_text")
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
                summary="Editorial/public page content mutation through Django Admin.",
                metadata={
                    "kind": obj.kind,
                    "slug": obj.slug,
                    "fromStatus": before_status,
                    "toStatus": obj.status,
                },
            )


@admin.register(SiteConfiguration)
class SiteConfigurationAdmin(admin.ModelAdmin):
    readonly_fields = ("key", "updated_at")
    fieldsets = (
        ("Identity", {"fields": ("business_name", "legal_name", "registration_number", "tax_identity")}),
        ("Contact", {"fields": ("support_email", "support_phone", "address", "business_hours", "social_links")}),
        ("Trust", {"fields": ("trust_marks", "payment_providers")}),
        ("Footer / SEO", {"fields": ("footer_tagline", "footer_description", "default_seo_title", "default_seo_description")}),
        ("System", {"fields": ("key", "updated_at")}),
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return super().has_add_permission(request) and not SiteConfiguration.objects.exists()

    def has_delete_permission(self, request: HttpRequest, obj: SiteConfiguration | None = None) -> bool:
        return False

    def save_model(self, request: HttpRequest, obj: SiteConfiguration, form: Any, change: bool) -> None:
        actor = _require_staff_user(request)
        with transaction.atomic():
            obj.full_clean()
            super().save_model(request, obj, form, change)
            append_audit_event(
                actor=actor,
                action="site.config.updated" if change else "site.config.created",
                object_type="content.SiteConfiguration",
                object_id=str(obj.pk),
                summary="Public site configuration changed through Django Admin.",
                metadata={"configured": True},
            )


@admin.register(HomepageBlock)
class HomepageBlockAdmin(admin.ModelAdmin):
    list_display = ("key", "block_type", "title", "is_enabled", "sort_order", "updated_at")
    list_filter = ("block_type", "is_enabled")
    search_fields = ("key", "title", "eyebrow", "body")
    ordering = ("sort_order", "id")

    def save_model(self, request: HttpRequest, obj: HomepageBlock, form: Any, change: bool) -> None:
        actor = _require_staff_user(request)
        with transaction.atomic():
            obj.full_clean()
            super().save_model(request, obj, form, change)
            append_audit_event(
                actor=actor,
                action="site.home_block.updated" if change else "site.home_block.created",
                object_type="content.HomepageBlock",
                object_id=str(obj.pk),
                summary="Homepage merchandising/content block changed through Django Admin.",
                metadata={"key": obj.key, "type": obj.block_type, "enabled": obj.is_enabled},
            )

    def delete_model(self, request: HttpRequest, obj: HomepageBlock) -> None:
        actor = _require_staff_user(request)
        object_id = str(obj.pk)
        metadata = {"key": obj.key, "type": obj.block_type}
        with transaction.atomic():
            super().delete_model(request, obj)
            append_audit_event(
                actor=actor,
                action="site.home_block.deleted",
                object_type="content.HomepageBlock",
                object_id=object_id,
                summary="Homepage block deleted through Django Admin.",
                metadata=metadata,
            )


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("created_at", "name", "email", "subject", "status")
    list_filter = ("status", "created_at")
    search_fields = ("name", "email", "subject", "message")
    ordering = ("-created_at",)
    readonly_fields = ("id", "name", "email", "subject", "message", "created_at", "updated_at")
    fields = ("id", "name", "email", "subject", "message", "status", "created_at", "updated_at")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: ContactMessage | None = None) -> bool:
        return False

    def save_model(self, request: HttpRequest, obj: ContactMessage, form: Any, change: bool) -> None:
        if not change:
            raise PermissionDenied("Contact messages can only be created through the public intake API.")
        actor = _require_staff_user(request)
        before = ContactMessage.objects.only("status").get(pk=obj.pk).status
        with transaction.atomic():
            super().save_model(request, obj, form, change)
            append_audit_event(
                actor=actor,
                action="contact.status.changed",
                object_type="content.ContactMessage",
                object_id=str(obj.pk),
                summary="Contact message workflow status changed through Django Admin.",
                metadata={"fromStatus": before, "toStatus": obj.status},
            )
