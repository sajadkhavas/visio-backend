from __future__ import annotations

from uuid import UUID

import pytest
from apps.accounts.models import User
from apps.catalog.models import Brand
from apps.catalog.staff_services import save_catalog_object_as_staff
from apps.content.models import ContactMessage, ContentEntry, HomepageBlock, SiteConfiguration
from apps.content.staff_services import (
    save_content_entry_as_staff,
    save_homepage_block_as_staff,
    save_site_configuration_as_staff,
    set_contact_message_status_as_staff,
)
from apps.operations.models import AuditEvent
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied
from django.utils import timezone

pytestmark = pytest.mark.django_db(transaction=True)


def permission(app_label: str, codename: str) -> Permission:
    return Permission.objects.get(content_type__app_label=app_label, codename=codename)


def staff_user(email: str, *permissions: Permission) -> User:
    user = User.objects.create_user(
        username=email,
        email=email,
        password="Correct-Horse-Battery-66",
        is_staff=True,
    )
    user.user_permissions.add(*permissions)
    return user


def test_catalog_staff_service_enforces_permission_and_appends_audit() -> None:
    denied = staff_user("catalog-denied@example.com")
    with pytest.raises(PermissionDenied):
        save_catalog_object_as_staff(
            denied,
            Brand(name="Denied", slug="denied"),
            change=False,
        )
    assert not Brand.objects.filter(slug="denied").exists()

    actor = staff_user(
        "catalog-add@example.com",
        permission("catalog", "add_brand"),
    )
    brand = save_catalog_object_as_staff(
        actor,
        Brand(name="VISIO Brand", slug="visio-brand"),
        change=False,
    )

    event = AuditEvent.objects.get(actor=actor, action="catalog.created")
    assert brand.pk is not None
    assert event.object_type == "catalog.Brand"
    assert event.object_id == str(brand.pk)


def test_content_entry_staff_service_preserves_publication_audit() -> None:
    actor = staff_user(
        "content-add@example.com",
        permission("content", "add_contententry"),
    )
    entry = ContentEntry(
        kind=ContentEntry.Kind.PAGE,
        slug="staff-page",
        title="Staff page",
        status=ContentEntry.Status.PUBLISHED,
        published_at=timezone.now(),
        body=[{"type": "paragraph", "text": "Managed content"}],
    )

    saved = save_content_entry_as_staff(actor, entry, change=False)

    event = AuditEvent.objects.get(actor=actor, action="content.created")
    assert saved.pk is not None
    assert event.metadata["kind"] == ContentEntry.Kind.PAGE
    assert event.metadata["toStatus"] == ContentEntry.Status.PUBLISHED


def test_site_and_homepage_services_require_native_django_permissions() -> None:
    actor = staff_user(
        "site-home@example.com",
        permission("content", "add_siteconfiguration"),
        permission("content", "add_homepageblock"),
    )

    config = save_site_configuration_as_staff(
        actor,
        SiteConfiguration(business_name="VISIO"),
        change=False,
    )
    block = save_homepage_block_as_staff(
        actor,
        HomepageBlock(
            key="merchant-hero",
            block_type=HomepageBlock.BlockType.HERO,
            title="VISIO Hero",
        ),
        change=False,
    )

    assert config.pk is not None
    assert block.pk is not None
    assert AuditEvent.objects.filter(actor=actor, action="site.config.created").count() == 1
    assert AuditEvent.objects.filter(actor=actor, action="site.home_block.created").count() == 1


def test_contact_status_service_changes_only_workflow_state_and_audits() -> None:
    message = ContactMessage.objects.create(
        name="Customer",
        email="customer@example.com",
        subject="Question",
        message="A customer message long enough for the workflow.",
    )
    original = {
        "name": message.name,
        "email": message.email,
        "subject": message.subject,
        "message": message.message,
    }
    actor = staff_user(
        "support-contact@example.com",
        permission("content", "change_contactmessage"),
    )

    updated = set_contact_message_status_as_staff(
        actor,
        message_id=UUID(str(message.pk)),
        status=ContactMessage.Status.RESOLVED,
    )

    assert updated.status == ContactMessage.Status.RESOLVED
    assert {
        "name": updated.name,
        "email": updated.email,
        "subject": updated.subject,
        "message": updated.message,
    } == original
    event = AuditEvent.objects.get(actor=actor, action="contact.status.changed")
    assert event.metadata == {
        "fromStatus": ContactMessage.Status.NEW,
        "toStatus": ContactMessage.Status.RESOLVED,
    }
