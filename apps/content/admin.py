from typing import Any
from uuid import UUID

from django.contrib import admin
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest

from apps.accounts.models import User

from .models import ContactMessage, ContentEntry, HomepageBlock, SiteConfiguration
from .staff_services import (
    delete_homepage_block_as_staff,
    save_content_entry_as_staff,
    save_homepage_block_as_staff,
    save_site_configuration_as_staff,
    set_contact_message_status_as_staff,
)


def _staff_actor(request: HttpRequest) -> User:
    actor = request.user
    if not isinstance(actor, User):
        raise PermissionDenied("Authenticated VISIO staff user required.")
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
        del form
        save_content_entry_as_staff(_staff_actor(request), obj, change=change)


@admin.register(SiteConfiguration)
class SiteConfigurationAdmin(admin.ModelAdmin):
    readonly_fields = ("key", "updated_at")
    fieldsets = (
        (
            "Identity",
            {"fields": ("business_name", "legal_name", "registration_number", "tax_identity")},
        ),
        (
            "Contact",
            {
                "fields": (
                    "support_email",
                    "support_phone",
                    "address",
                    "business_hours",
                    "social_links",
                )
            },
        ),
        ("Trust", {"fields": ("trust_marks", "payment_providers")}),
        (
            "Footer / SEO",
            {
                "fields": (
                    "footer_tagline",
                    "footer_description",
                    "default_seo_title",
                    "default_seo_description",
                )
            },
        ),
        ("System", {"fields": ("key", "updated_at")}),
    )

    def has_add_permission(self, request: HttpRequest) -> bool:
        return super().has_add_permission(request) and not SiteConfiguration.objects.exists()

    def has_delete_permission(
        self, request: HttpRequest, obj: SiteConfiguration | None = None
    ) -> bool:
        return False

    def save_model(
        self,
        request: HttpRequest,
        obj: SiteConfiguration,
        form: Any,
        change: bool,
    ) -> None:
        del form
        save_site_configuration_as_staff(_staff_actor(request), obj, change=change)


@admin.register(HomepageBlock)
class HomepageBlockAdmin(admin.ModelAdmin):
    list_display = ("key", "block_type", "title", "is_enabled", "sort_order", "updated_at")
    list_filter = ("block_type", "is_enabled")
    search_fields = ("key", "title", "eyebrow", "body")
    ordering = ("sort_order", "id")

    def save_model(
        self,
        request: HttpRequest,
        obj: HomepageBlock,
        form: Any,
        change: bool,
    ) -> None:
        del form
        save_homepage_block_as_staff(_staff_actor(request), obj, change=change)

    def delete_model(self, request: HttpRequest, obj: HomepageBlock) -> None:
        delete_homepage_block_as_staff(_staff_actor(request), obj)


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

    def has_delete_permission(
        self, request: HttpRequest, obj: ContactMessage | None = None
    ) -> bool:
        return False

    def save_model(
        self,
        request: HttpRequest,
        obj: ContactMessage,
        form: Any,
        change: bool,
    ) -> None:
        del form
        if not change or obj.pk is None:
            raise PermissionDenied(
                "Contact messages can only be created through the public intake API."
            )
        updated = set_contact_message_status_as_staff(
            _staff_actor(request),
            message_id=UUID(str(obj.pk)),
            status=obj.status,
        )
        obj.status = updated.status
        obj.updated_at = updated.updated_at
