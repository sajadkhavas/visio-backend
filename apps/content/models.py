from __future__ import annotations

from typing import Any
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import models


def _flatten_text(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        parts: list[str] = []
        for nested in value.values():
            parts.extend(_flatten_text(nested))
        return parts
    if isinstance(value, list):
        parts = []
        for nested in value:
            parts.extend(_flatten_text(nested))
        return parts
    return []


class ContentEntry(models.Model):
    class Kind(models.TextChoices):
        GUIDE = "guide", "Guide"
        MAGAZINE = "magazine", "Magazine"
        POLICY = "policy", "Policy"
        PAGE = "page", "Page"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    class AuthorKind(models.TextChoices):
        ORGANIZATION = "organization", "Organization"
        PERSON = "person", "Person"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    kind = models.CharField(max_length=16, choices=Kind.choices)
    slug = models.SlugField(max_length=180, allow_unicode=True)
    title = models.CharField(max_length=240)
    excerpt = models.TextField(blank=True)
    direct_answer = models.TextField(blank=True)
    audience_boundary = models.TextField(blank=True)
    article_type = models.CharField(max_length=40, blank=True)
    author_name = models.CharField(max_length=180, default="تحریریه VISIO")
    author_kind = models.CharField(
        max_length=16,
        choices=AuthorKind.choices,
        default=AuthorKind.ORGANIZATION,
    )
    reviewer_name = models.CharField(max_length=180, blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    modified_at = models.DateTimeField(null=True, blank=True)
    review_due_at = models.DateField(null=True, blank=True)
    body = models.JSONField(default=list, blank=True)
    sources = models.JSONField(default=list, blank=True)
    media = models.JSONField(default=dict, blank=True)
    related_slugs = models.JSONField(default=list, blank=True)
    seo_title = models.CharField(max_length=240, blank=True)
    seo_description = models.CharField(max_length=320, blank=True)
    search_text = models.TextField(blank=True, editable=False, default="")
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "-published_at", "title", "id")
        indexes = [
            models.Index(
                fields=("status", "kind", "published_at", "sort_order"),
                name="content_public_idx",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=("kind", "slug"),
                name="content_kind_slug_uq",
            ),
            models.CheckConstraint(
                condition=(~models.Q(status="published") | models.Q(published_at__isnull=False)),
                name="content_publish_time",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.kind}:{self.slug}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.search_text = self.rebuild_search_text()
        super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if not isinstance(self.body, list):
            errors["body"] = "Content body must be a JSON array of editorial blocks."
        if not isinstance(self.sources, list):
            errors["sources"] = "Sources must be a JSON array."
        if not isinstance(self.media, dict):
            errors["media"] = "Media must be a JSON object."
        if not isinstance(self.related_slugs, list) or not all(
            isinstance(item, str) for item in self.related_slugs
        ):
            errors["related_slugs"] = "Related slugs must be a JSON array of strings."
        if errors:
            raise ValidationError(errors)

    def rebuild_search_text(self) -> str:
        fields: list[object] = [
            self.title,
            self.excerpt,
            self.direct_answer,
            self.audience_boundary,
            self.article_type,
            self.author_name,
            self.body,
            self.sources,
        ]
        terms: list[str] = []
        for value in fields:
            terms.extend(_flatten_text(value))
        return "\n".join(term.strip() for term in terms if term.strip())


class SiteConfiguration(models.Model):
    key = models.CharField(max_length=32, unique=True, default="default", editable=False)
    business_name = models.CharField(max_length=180, blank=True)
    legal_name = models.CharField(max_length=220, blank=True)
    registration_number = models.CharField(max_length=80, blank=True)
    tax_identity = models.CharField(max_length=80, blank=True)
    support_email = models.EmailField(blank=True)
    support_phone = models.CharField(max_length=40, blank=True)
    address = models.TextField(blank=True)
    business_hours = models.TextField(blank=True)
    social_links = models.JSONField(default=list, blank=True)
    trust_marks = models.JSONField(default=list, blank=True)
    payment_providers = models.JSONField(default=list, blank=True)
    footer_tagline = models.CharField(max_length=220, blank=True)
    footer_description = models.CharField(max_length=400, blank=True)
    default_seo_title = models.CharField(max_length=240, blank=True)
    default_seo_description = models.CharField(max_length=320, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Site configuration"
        verbose_name_plural = "Site configuration"

    def __str__(self) -> str:
        return "VISIO public site configuration"

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        for field_name in ("social_links", "trust_marks", "payment_providers"):
            value = getattr(self, field_name)
            if not isinstance(value, list):
                errors[field_name] = "Value must be a JSON array."
        if errors:
            raise ValidationError(errors)


class HomepageBlock(models.Model):
    class BlockType(models.TextChoices):
        HERO = "hero", "Hero"
        CATEGORY = "category", "Category merchandising"
        EDITORIAL = "editorial", "Editorial"
        GUIDE = "guide", "Guide"
        DETAIL = "detail", "Detail study"
        FEATURED = "featured", "Featured collection"

    key = models.SlugField(max_length=100, unique=True)
    block_type = models.CharField(max_length=20, choices=BlockType.choices)
    eyebrow = models.CharField(max_length=160, blank=True)
    title = models.CharField(max_length=240)
    body = models.TextField(blank=True)
    image = models.FileField(upload_to="site/home/", blank=True)
    image_alt = models.CharField(max_length=240, blank=True)
    target_path = models.CharField(max_length=300, blank=True)
    target_label = models.CharField(max_length=120, blank=True)
    payload = models.JSONField(default=dict, blank=True)
    is_enabled = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "id")
        indexes = [
            models.Index(fields=("is_enabled", "sort_order"), name="content_home_public_idx")
        ]

    def __str__(self) -> str:
        return f"{self.block_type}:{self.key}"

    def clean(self) -> None:
        super().clean()
        if not isinstance(self.payload, dict):
            raise ValidationError({"payload": "Homepage payload must be a JSON object."})


class ContactMessage(models.Model):
    class Status(models.TextChoices):
        NEW = "new", "New"
        READ = "read", "Read"
        RESOLVED = "resolved", "Resolved"
        SPAM = "spam", "Spam"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    name = models.CharField(max_length=180)
    email = models.EmailField()
    subject = models.CharField(max_length=240)
    message = models.TextField(max_length=5000)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.NEW)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at", "id")
        indexes = [models.Index(fields=("status", "created_at"), name="content_contact_status_idx")]

    def __str__(self) -> str:
        return f"{self.created_at:%Y-%m-%d} · {self.subject}"
