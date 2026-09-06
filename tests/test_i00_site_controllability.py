from __future__ import annotations

from uuid import UUID

import pytest
from apps.content.models import ContactMessage, ContentEntry, HomepageBlock, SiteConfiguration
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client
from django.utils import timezone

pytestmark = pytest.mark.django_db(transaction=True)


def test_public_site_config_fails_closed_until_configured() -> None:
    response = Client().get("/api/v1/site/config/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is False
    assert payload["supportEmail"] == ""
    assert payload["trustMarks"] == []


def test_public_site_config_exposes_only_public_operator_managed_values() -> None:
    SiteConfiguration.objects.create(
        business_name="VISIO",
        support_email="support@example.com",
        support_phone="02100000000",
        address="Tehran",
        business_hours="09:00-18:00",
        social_links=[{"label": "Instagram", "url": "https://example.com/visio"}],
        trust_marks=[{"label": "Verified", "url": "https://example.com/trust"}],
        payment_providers=[{"name": "ZarinPal", "enabled": True}],
        footer_tagline="تناسب دقیق، سبک ماندگار.",
        footer_description="راهنمایی روشن برای انتخاب فریم.",
        default_seo_title="VISIO",
        default_seo_description="Eyewear",
    )

    response = Client().get("/api/v1/site/config/")
    assert response.status_code == 200
    payload = response.json()
    assert payload["configured"] is True
    assert payload["businessName"] == "VISIO"
    assert payload["supportEmail"] == "support@example.com"
    assert payload["paymentProviders"] == [{"name": "ZarinPal", "enabled": True}]
    assert "merchant" not in str(payload).lower()


def test_homepage_api_returns_only_enabled_blocks_in_operator_order() -> None:
    HomepageBlock.objects.create(
        key="second",
        block_type=HomepageBlock.BlockType.EDITORIAL,
        title="Second",
        sort_order=20,
        is_enabled=True,
    )
    HomepageBlock.objects.create(
        key="first",
        block_type=HomepageBlock.BlockType.HERO,
        title="First",
        image=SimpleUploadedFile("hero.jpg", b"not-a-real-image", content_type="image/jpeg"),
        sort_order=10,
        is_enabled=True,
    )
    HomepageBlock.objects.create(
        key="hidden",
        block_type=HomepageBlock.BlockType.FEATURED,
        title="Hidden",
        sort_order=0,
        is_enabled=False,
    )

    response = Client().get("/api/v1/site/home/")
    assert response.status_code == 200
    blocks = response.json()["blocks"]
    assert [block["key"] for block in blocks] == ["first", "second"]
    assert blocks[0]["blockType"] == "hero"
    assert blocks[0]["imageUrl"].endswith("/media/site/home/hero.jpg")


def test_content_page_kind_is_publicly_retrievable_only_when_published() -> None:
    ContentEntry.objects.create(
        kind=ContentEntry.Kind.PAGE,
        slug="about",
        title="About VISIO",
        status=ContentEntry.Status.DRAFT,
        body=[{"type": "paragraph", "text": "draft"}],
    )
    assert Client().get("/api/v1/content/page/about/").status_code == 404

    page = ContentEntry.objects.get(kind=ContentEntry.Kind.PAGE, slug="about")
    page.status = ContentEntry.Status.PUBLISHED
    page.published_at = timezone.now()
    page.save()

    response = Client().get("/api/v1/content/page/about/")
    assert response.status_code == 200
    assert response.json()["kind"] == "page"
    assert response.json()["title"] == "About VISIO"


def test_contact_intake_requires_csrf_and_persists_only_valid_messages() -> None:
    client = Client(enforce_csrf_checks=True)
    body = {
        "name": "Sajad",
        "email": "sajad@example.com",
        "subject": "Product question",
        "message": "I need more information about this frame.",
    }

    rejected = client.post("/api/v1/contact/messages/", data=body, content_type="application/json")
    assert rejected.status_code == 403
    assert ContactMessage.objects.count() == 0

    csrf_response = client.get("/api/v1/auth/csrf/")
    token = csrf_response.json()["csrf_token"]
    accepted = client.post(
        "/api/v1/contact/messages/",
        data=body,
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert accepted.status_code == 201
    assert UUID(accepted.json()["id"])
    assert accepted.json()["status"] == "received"
    message = ContactMessage.objects.get()
    assert message.status == ContactMessage.Status.NEW
    assert message.email == "sajad@example.com"


def test_contact_intake_rejects_short_payload() -> None:
    client = Client(enforce_csrf_checks=True)
    token = client.get("/api/v1/auth/csrf/").json()["csrf_token"]
    response = client.post(
        "/api/v1/contact/messages/",
        data={"name": "x", "email": "bad", "subject": "x", "message": "short"},
        content_type="application/json",
        HTTP_X_CSRFTOKEN=token,
    )
    assert response.status_code == 400
    assert ContactMessage.objects.count() == 0


def test_site_configuration_is_singleton_by_database_constraint() -> None:
    SiteConfiguration.objects.create(business_name="VISIO")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            SiteConfiguration.objects.create(business_name="Duplicate")
