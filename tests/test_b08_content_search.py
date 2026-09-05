from datetime import timedelta

import pytest
from apps.catalog.models import Brand, Category, Product, ProductMedia
from apps.content.models import ContentEntry
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import IntegrityError, transaction
from django.test import Client
from django.utils import timezone

pytestmark = pytest.mark.django_db

CONTENT_PATH = "/api/v1/content/"
PRODUCTS_PATH = "/api/v1/catalog/products/"


def create_content(
    *,
    kind: str = ContentEntry.Kind.GUIDE,
    slug: str,
    title: str,
    excerpt: str = "",
    status: str = ContentEntry.Status.PUBLISHED,
    published_offset: timedelta = timedelta(0),
    body: list[dict[str, object]] | None = None,
    seo_title: str = "",
    seo_description: str = "",
) -> ContentEntry:
    published_at = timezone.now() + published_offset if status == ContentEntry.Status.PUBLISHED else None
    return ContentEntry.objects.create(
        kind=kind,
        slug=slug,
        title=title,
        excerpt=excerpt,
        direct_answer="پاسخ مستقیم",
        audience_boundary="مرز استفاده عمومی",
        author_name="تحریریه VISIO",
        author_kind=ContentEntry.AuthorKind.ORGANIZATION,
        status=status,
        published_at=published_at,
        body=body or [{"type": "paragraph", "text": "متن عمومی"}],
        sources=[],
        media={"image": None, "alt": "", "credit": None, "rightsStatus": "not-required"},
        related_slugs=[],
        seo_title=seo_title,
        seo_description=seo_description,
    )


def create_product(
    *,
    name: str,
    slug: str,
    brand: Brand,
    category: Category,
    material: str,
    published_offset: timedelta = timedelta(0),
) -> Product:
    product = Product.objects.create(
        name=name,
        slug=slug,
        brand=brand,
        category=category,
        status=Product.Status.PUBLISHED,
        published_at=timezone.now() + published_offset,
        material=material,
        shape="گرد",
        color="مشکی",
    )
    ProductMedia.objects.create(
        product=product,
        file=SimpleUploadedFile(f"{slug}.jpg", b"b08-media", content_type="image/jpeg"),
        alt=f"{name} front",
        position=0,
    )
    return product


def test_content_public_visibility_and_frontend_contract() -> None:
    visible = create_content(
        slug="choose-eyeglasses",
        title="چطور یک فریم را آگاهانه انتخاب کنیم؟",
        excerpt="راهنمای انتخاب فریم",
        seo_title="راهنمای انتخاب فریم عینک | VISIO",
        seo_description="راهنمای مرحله‌به‌مرحله برای انتخاب فریم.",
    )
    create_content(
        slug="future-guide",
        title="Future",
        published_offset=timedelta(days=1),
    )
    create_content(
        slug="draft-guide",
        title="Draft",
        status=ContentEntry.Status.DRAFT,
    )
    create_content(
        slug="archived-guide",
        title="Archived",
        status=ContentEntry.Status.ARCHIVED,
    )

    response = Client().get(CONTENT_PATH, {"kind": "guide"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["count"] == 1
    item = payload["results"][0]
    assert item["id"] == str(visible.id)
    assert item["kind"] == "guide"
    assert item["slug"] == "choose-eyeglasses"
    assert item["source"] == "backend"
    assert item["authoritative"] is True
    assert item["author"] == {"name": "تحریریه VISIO", "kind": "organization"}
    assert item["directAnswer"] == "پاسخ مستقیم"
    assert item["audienceAndBoundary"] == "مرز استفاده عمومی"
    assert item["seo"] == {
        "title": "راهنمای انتخاب فریم عینک | VISIO",
        "description": "راهنمای مرحله‌به‌مرحله برای انتخاب فریم.",
    }


def test_content_search_filter_sort_pagination_and_unknown_params() -> None:
    create_content(
        slug="size-guide",
        title="راهنمای اندازه فریم",
        excerpt="اعداد روی فریم",
        body=[{"type": "paragraph", "text": "عرض عدسی و پل به میلی متر"}],
    )
    create_content(
        slug="care-guide",
        title="مراقبت از عینک",
        excerpt="روش نگهداری",
        body=[{"type": "paragraph", "text": "تمیز کردن عدسی"}],
    )
    create_content(
        kind=ContentEntry.Kind.MAGAZINE,
        slug="design-story",
        title="داستان طراحی",
        excerpt="روایت فریم",
    )

    searched = Client().get(CONTENT_PATH, {"kind": "guide", "q": "عدسی پل"})
    assert searched.status_code == 200
    assert [item["slug"] for item in searched.json()["results"]] == ["size-guide"]

    paged = Client().get(CONTENT_PATH, {"kind": "guide", "page_size": 1, "sort": "title-asc"})
    assert paged.status_code == 200
    assert paged.json()["count"] == 2
    assert len(paged.json()["results"]) == 1

    assert Client().get(CONTENT_PATH, {"kind": "unknown"}).status_code == 400
    assert Client().get(CONTENT_PATH, {"sort": "random"}).status_code == 400
    assert Client().get(CONTENT_PATH, {"private": "1"}).status_code == 400
    assert Client().get(CONTENT_PATH, {"q": "x" * 121}).status_code == 400


def test_content_detail_is_kind_scoped_and_unpublished_content_never_leaks() -> None:
    create_content(slug="shared", title="Published guide")
    create_content(
        kind=ContentEntry.Kind.MAGAZINE,
        slug="shared",
        title="Published magazine",
    )
    create_content(
        slug="future",
        title="Future guide",
        published_offset=timedelta(days=1),
    )

    guide = Client().get(f"{CONTENT_PATH}guide/shared/")
    magazine = Client().get(f"{CONTENT_PATH}magazine/shared/")

    assert guide.status_code == 200
    assert guide.json()["title"] == "Published guide"
    assert magazine.status_code == 200
    assert magazine.json()["title"] == "Published magazine"
    assert Client().get(f"{CONTENT_PATH}guide/future/").status_code == 404
    assert Client().get(f"{CONTENT_PATH}policy/shared/").status_code == 404


def test_content_model_validation_and_publication_database_constraint() -> None:
    invalid = ContentEntry(
        kind=ContentEntry.Kind.GUIDE,
        slug="invalid-body",
        title="Invalid",
        body={"type": "paragraph"},
        sources=[],
        media={},
        related_slugs=[],
    )
    with pytest.raises(DjangoValidationError):
        invalid.full_clean()

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            ContentEntry.objects.create(
                kind=ContentEntry.Kind.GUIDE,
                slug="published-without-time",
                title="Invalid published",
                status=ContentEntry.Status.PUBLISHED,
                published_at=None,
            )


def test_catalog_search_is_backend_authoritative_public_only_and_bounded() -> None:
    brand = Brand.objects.create(name="VISIO Lab", slug="visio-lab")
    category = Category.objects.create(name="فریم طبی", slug="optical")
    visible = create_product(
        name="فریم آلفا",
        slug="alpha",
        brand=brand,
        category=category,
        material="تیتانیوم سبک",
    )
    create_product(
        name="فریم آینده",
        slug="future-product",
        brand=brand,
        category=category,
        material="تیتانیوم سبک",
        published_offset=timedelta(days=1),
    )
    create_product(
        name="فریم بتا",
        slug="beta",
        brand=brand,
        category=category,
        material="استیل",
    )

    response = Client().get(PRODUCTS_PATH, {"q": "تیتانیوم آلفا"})

    assert response.status_code == 200
    assert response.json()["count"] == 1
    item = response.json()["results"][0]
    assert item["id"] == str(visible.id)
    assert item["source"] == "backend"
    assert item["authoritative"] is True

    assert Client().get(PRODUCTS_PATH, {"q": "x" * 121}).status_code == 400
    assert Client().get(PRODUCTS_PATH, {"clientFixture": "1"}).status_code == 400
