from django.contrib import admin

from .models import ContentEntry


@admin.register(ContentEntry)
class ContentEntryAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "status", "published_at", "updated_at")
    list_filter = ("kind", "status", "author_kind")
    search_fields = ("title", "slug", "excerpt", "author_name")
    ordering = ("-published_at", "sort_order", "title")
    readonly_fields = ("search_text", "created_at", "updated_at")
