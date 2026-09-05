from __future__ import annotations

from django.db.models import Q, QuerySet
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny

from .models import ContentEntry
from .pagination import ContentPagination
from .serializers import ContentEntrySerializer

CONTENT_QUERY_PARAMETERS = {"kind", "q", "sort", "page", "page_size"}
CONTENT_SORT_VALUES = {"default", "newest", "oldest", "title-asc", "title-desc"}


def public_content_queryset() -> QuerySet[ContentEntry]:
    return ContentEntry.objects.filter(
        status=ContentEntry.Status.PUBLISHED,
        published_at__isnull=False,
        published_at__lte=timezone.now(),
    )


def _reject_unknown_parameters(query_params: object) -> None:
    keys = set(query_params.keys())  # type: ignore[attr-defined]
    unknown = sorted(keys - CONTENT_QUERY_PARAMETERS)
    if unknown:
        raise ValidationError({"query": f"Unsupported query parameter(s): {', '.join(unknown)}"})


def _validated_query(value: object) -> str:
    if value is None:
        return ""
    query = str(value).strip()
    if len(query) > 120:
        raise ValidationError({"q": "Search query must be at most 120 characters."})
    return query


def validated_content_queryset(query_params: object) -> QuerySet[ContentEntry]:
    _reject_unknown_parameters(query_params)
    queryset = public_content_queryset()

    kind = query_params.get("kind")  # type: ignore[attr-defined]
    if kind:
        valid_kinds = {choice.value for choice in ContentEntry.Kind}
        if kind not in valid_kinds:
            raise ValidationError({"kind": "Allowed values: guide, magazine, policy."})
        queryset = queryset.filter(kind=kind)

    query = _validated_query(query_params.get("q"))  # type: ignore[attr-defined]
    if query:
        for term in query.split():
            queryset = queryset.filter(
                Q(title__icontains=term)
                | Q(excerpt__icontains=term)
                | Q(direct_answer__icontains=term)
                | Q(audience_boundary__icontains=term)
                | Q(search_text__icontains=term)
            )

    sort = str(query_params.get("sort", "default"))  # type: ignore[attr-defined]
    if sort not in CONTENT_SORT_VALUES:
        raise ValidationError(
            {"sort": "Allowed values: default, newest, oldest, title-asc, title-desc."}
        )
    if sort in {"default", "newest"}:
        return queryset.order_by("-published_at", "sort_order", "title", "id")
    if sort == "oldest":
        return queryset.order_by("published_at", "sort_order", "title", "id")
    if sort == "title-asc":
        return queryset.order_by("title", "id")
    return queryset.order_by("-title", "id")


@extend_schema(
    parameters=[
        OpenApiParameter("kind", str, enum=["guide", "magazine", "policy"]),
        OpenApiParameter("q", str, description="Backend-authoritative text search, max 120 chars."),
        OpenApiParameter(
            "sort",
            str,
            enum=["default", "newest", "oldest", "title-asc", "title-desc"],
        ),
        OpenApiParameter("page", int),
        OpenApiParameter("page_size", int, description="Maximum 48."),
    ]
)
class ContentListView(ListAPIView):
    serializer_class = ContentEntrySerializer
    permission_classes = (AllowAny,)
    authentication_classes: tuple[()] = ()
    pagination_class = ContentPagination

    def get_queryset(self) -> QuerySet[ContentEntry]:
        return validated_content_queryset(self.request.query_params)


class ContentDetailView(RetrieveAPIView):
    serializer_class = ContentEntrySerializer
    permission_classes = (AllowAny,)
    authentication_classes: tuple[()] = ()
    lookup_field = "slug"
    lookup_url_kwarg = "slug"

    def get_queryset(self) -> QuerySet[ContentEntry]:
        return public_content_queryset().filter(kind=self.kwargs["kind"])
