from __future__ import annotations

from django.http import HttpRequest
from rest_framework import serializers

from .models import ContactMessage, ContentEntry, HomepageBlock, SiteConfiguration


class ContentEntrySerializer(serializers.ModelSerializer):
    directAnswer = serializers.CharField(source="direct_answer", read_only=True)
    audienceAndBoundary = serializers.CharField(source="audience_boundary", read_only=True)
    articleType = serializers.CharField(source="article_type", read_only=True)
    author = serializers.SerializerMethodField()
    reviewer = serializers.SerializerMethodField()
    publishedAt = serializers.DateTimeField(source="published_at", read_only=True)
    modifiedAt = serializers.DateTimeField(source="modified_at", read_only=True)
    reviewDueAt = serializers.DateField(source="review_due_at", read_only=True)
    relatedGuideSlugs = serializers.JSONField(source="related_slugs", read_only=True)
    seo = serializers.SerializerMethodField()
    source = serializers.SerializerMethodField()
    authoritative = serializers.SerializerMethodField()

    class Meta:
        model = ContentEntry
        fields = (
            "id",
            "kind",
            "slug",
            "title",
            "excerpt",
            "directAnswer",
            "audienceAndBoundary",
            "articleType",
            "author",
            "reviewer",
            "publishedAt",
            "modifiedAt",
            "reviewDueAt",
            "body",
            "sources",
            "media",
            "relatedGuideSlugs",
            "seo",
            "source",
            "authoritative",
        )

    def get_author(self, entry: ContentEntry) -> dict[str, str]:
        return {"name": entry.author_name, "kind": entry.author_kind}

    def get_reviewer(self, entry: ContentEntry) -> str | None:
        return entry.reviewer_name or None

    def get_seo(self, entry: ContentEntry) -> dict[str, str]:
        title = entry.seo_title or f"{entry.title} | VISIO"
        description = entry.seo_description or entry.excerpt
        return {"title": title, "description": description}

    def get_source(self, entry: ContentEntry) -> str:
        return "backend"

    def get_authoritative(self, entry: ContentEntry) -> bool:
        return True


class SiteConfigurationSerializer(serializers.ModelSerializer):
    businessName = serializers.CharField(source="business_name", read_only=True)
    legalName = serializers.CharField(source="legal_name", read_only=True)
    registrationNumber = serializers.CharField(source="registration_number", read_only=True)
    taxIdentity = serializers.CharField(source="tax_identity", read_only=True)
    supportEmail = serializers.EmailField(source="support_email", read_only=True)
    supportPhone = serializers.CharField(source="support_phone", read_only=True)
    businessHours = serializers.CharField(source="business_hours", read_only=True)
    socialLinks = serializers.JSONField(source="social_links", read_only=True)
    trustMarks = serializers.JSONField(source="trust_marks", read_only=True)
    paymentProviders = serializers.JSONField(source="payment_providers", read_only=True)
    footerTagline = serializers.CharField(source="footer_tagline", read_only=True)
    footerDescription = serializers.CharField(source="footer_description", read_only=True)
    defaultSeo = serializers.SerializerMethodField()
    configured = serializers.SerializerMethodField()

    class Meta:
        model = SiteConfiguration
        fields = (
            "configured",
            "businessName",
            "legalName",
            "registrationNumber",
            "taxIdentity",
            "supportEmail",
            "supportPhone",
            "address",
            "businessHours",
            "socialLinks",
            "trustMarks",
            "paymentProviders",
            "footerTagline",
            "footerDescription",
            "defaultSeo",
            "updated_at",
        )

    def get_defaultSeo(self, config: SiteConfiguration) -> dict[str, str]:
        return {
            "title": config.default_seo_title,
            "description": config.default_seo_description,
        }

    def get_configured(self, config: SiteConfiguration) -> bool:
        return True


class HomepageBlockSerializer(serializers.ModelSerializer):
    blockType = serializers.CharField(source="block_type", read_only=True)
    imageUrl = serializers.SerializerMethodField()
    imageAlt = serializers.CharField(source="image_alt", read_only=True)
    targetPath = serializers.CharField(source="target_path", read_only=True)
    targetLabel = serializers.CharField(source="target_label", read_only=True)
    sortOrder = serializers.IntegerField(source="sort_order", read_only=True)

    class Meta:
        model = HomepageBlock
        fields = (
            "key",
            "blockType",
            "eyebrow",
            "title",
            "body",
            "imageUrl",
            "imageAlt",
            "targetPath",
            "targetLabel",
            "payload",
            "sortOrder",
        )

    def get_imageUrl(self, block: HomepageBlock) -> str:
        if not block.image:
            return ""
        request = self.context.get("request")
        url = block.image.url
        if isinstance(request, HttpRequest):
            return request.build_absolute_uri(url)
        return url


class ContactMessageCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = ContactMessage
        fields = ("name", "email", "subject", "message")

    def validate_name(self, value: str) -> str:
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("Name must contain at least 2 characters.")
        return value

    def validate_subject(self, value: str) -> str:
        value = value.strip()
        if len(value) < 3:
            raise serializers.ValidationError("Subject must contain at least 3 characters.")
        return value

    def validate_message(self, value: str) -> str:
        value = value.strip()
        if len(value) < 10:
            raise serializers.ValidationError("Message must contain at least 10 characters.")
        return value
