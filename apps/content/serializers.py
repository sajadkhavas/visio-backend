from __future__ import annotations

from typing import Any

from rest_framework import serializers

from .models import ContentEntry


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
        return {
            "name": entry.author_name,
            "kind": entry.author_kind,
        }

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


class PublicSearchResultSerializer(serializers.Serializer):
    type = serializers.ChoiceField(choices=("product", "content"))
    slug = serializers.CharField()
    title = serializers.CharField()
    subtitle = serializers.CharField(allow_blank=True)
    kind = serializers.CharField(allow_blank=True)
    url = serializers.CharField()
    score = serializers.FloatField()
    payload = serializers.DictField(child=serializers.JSONField())

    def to_representation(self, instance: Any) -> dict[str, Any]:
        return dict(super().to_representation(instance))
