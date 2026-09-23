from __future__ import annotations

from uuid import UUID

from django.db import transaction

from apps.accounts.models import User
from apps.operations.audit import append_audit_event
from apps.operations.permissions import require_staff_permission

from .models import ContactMessage, ContentEntry, HomepageBlock, SiteConfiguration


def _permission(model_name: str, *, change: bool) -> str:
    action = "change" if change else "add"
    return f"content.{action}_{model_name}"


def save_content_entry_as_staff(
    actor: User,
    entry: ContentEntry,
    *,
    change: bool,
) -> ContentEntry:
    require_staff_permission(actor, _permission("contententry", change=change))

    with transaction.atomic():
        before_status = None
        if change and entry.pk:
            before_status = (
                ContentEntry.objects.select_for_update()
                .only("status")
                .get(pk=entry.pk)
                .status
            )
        entry.full_clean()
        entry.save()
        append_audit_event(
            actor=actor,
            action="content.updated" if change else "content.created",
            object_type="content.ContentEntry",
            object_id=str(entry.pk),
            summary="Editorial/public content mutation through the staff service boundary.",
            metadata={
                "kind": entry.kind,
                "slug": entry.slug,
                "fromStatus": before_status,
                "toStatus": entry.status,
            },
        )
    return entry


def save_site_configuration_as_staff(
    actor: User,
    config: SiteConfiguration,
    *,
    change: bool,
) -> SiteConfiguration:
    require_staff_permission(actor, _permission("siteconfiguration", change=change))

    with transaction.atomic():
        config.full_clean()
        config.save()
        append_audit_event(
            actor=actor,
            action="site.config.updated" if change else "site.config.created",
            object_type="content.SiteConfiguration",
            object_id=str(config.pk),
            summary="Public site configuration changed through the staff service boundary.",
            metadata={"configured": True},
        )
    return config


def save_homepage_block_as_staff(
    actor: User,
    block: HomepageBlock,
    *,
    change: bool,
) -> HomepageBlock:
    require_staff_permission(actor, _permission("homepageblock", change=change))

    with transaction.atomic():
        block.full_clean()
        block.save()
        append_audit_event(
            actor=actor,
            action="site.home_block.updated" if change else "site.home_block.created",
            object_type="content.HomepageBlock",
            object_id=str(block.pk),
            summary="Homepage block changed through the staff service boundary.",
            metadata={
                "key": block.key,
                "type": block.block_type,
                "enabled": block.is_enabled,
            },
        )
    return block


def delete_homepage_block_as_staff(
    actor: User,
    block: HomepageBlock,
) -> None:
    require_staff_permission(actor, "content.delete_homepageblock")
    object_id = str(block.pk)
    metadata = {"key": block.key, "type": block.block_type}

    with transaction.atomic():
        block.delete()
        append_audit_event(
            actor=actor,
            action="site.home_block.deleted",
            object_type="content.HomepageBlock",
            object_id=object_id,
            summary="Homepage block deleted through the staff service boundary.",
            metadata=metadata,
        )


def set_contact_message_status_as_staff(
    actor: User,
    *,
    message_id: UUID,
    status: str,
) -> ContactMessage:
    require_staff_permission(actor, "content.change_contactmessage")

    with transaction.atomic():
        message = ContactMessage.objects.select_for_update().get(pk=message_id)
        before_status = message.status
        message.status = status
        message.full_clean()
        message.save(update_fields=("status", "updated_at"))
        append_audit_event(
            actor=actor,
            action="contact.status.changed",
            object_type="content.ContactMessage",
            object_id=str(message.pk),
            summary="Contact workflow status changed through the staff service boundary.",
            metadata={"fromStatus": before_status, "toStatus": message.status},
        )
    return message
