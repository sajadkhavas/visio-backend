from typing import Any

from rest_framework import serializers

from .models import (
    Brand,
    Category,
    Product,
    ProductBadge,
    ProductMedia,
    ProductOption,
    ProductVariant,
)


def media_payload(media: ProductMedia, request: Any) -> dict[str, Any]:
    url = media.file.url
    if request is not None:
        url = request.build_absolute_uri(url)
    payload: dict[str, Any] = {
        "id": str(media.id),
        "url": url,
        "alt": media.alt,
        "width": media.width,
        "height": media.height,
        "position": media.position,
    }
    if media.variant_id is not None:
        payload["variantId"] = str(media.variant_id)
    return payload


class BrandSerializer(serializers.ModelSerializer):
    class Meta:
        model = Brand
        fields = ("id", "slug", "name")


class CategorySerializer(serializers.ModelSerializer):
    parentSlug = serializers.CharField(source="parent.slug", allow_null=True, read_only=True)

    class Meta:
        model = Category
        fields = ("id", "slug", "name", "parentSlug")


class ProductSerializer(serializers.ModelSerializer):
    brand = serializers.CharField(source="brand.name", read_only=True)
    category = serializers.CharField(source="category.slug", read_only=True)
    source = serializers.SerializerMethodField()
    authoritative = serializers.SerializerMethodField()
    images = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    priceContract = serializers.SerializerMethodField()
    price = serializers.SerializerMethodField()
    availability = serializers.SerializerMethodField()
    inStock = serializers.SerializerMethodField()
    dimensions = serializers.SerializerMethodField()
    options = serializers.SerializerMethodField()
    variants = serializers.SerializerMethodField()
    defaultVariantId = serializers.SerializerMethodField()
    badges = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = (
            "id",
            "slug",
            "name",
            "brand",
            "category",
            "source",
            "authoritative",
            "images",
            "image",
            "priceContract",
            "price",
            "availability",
            "inStock",
            "shape",
            "material",
            "color",
            "dimensions",
            "options",
            "variants",
            "defaultVariantId",
            "badges",
        )

    def get_source(self, product: Product) -> str:
        return "backend"

    def get_authoritative(self, product: Product) -> bool:
        return True

    def get_images(self, product: Product) -> list[dict[str, Any]]:
        request = self.context.get("request")
        return [
            media_payload(media, request)
            for media in product.media.all()
            if media.is_active and media.variant_id is None
        ]

    def get_image(self, product: Product) -> str:
        images = self.get_images(product)
        return str(images[0]["url"]) if images else ""

    def get_priceContract(self, product: Product) -> dict[str, Any]:
        return {
            "current": None,
            "compareAt": None,
            "authoritative": False,
            "source": "backend",
            "updatedAt": None,
        }

    def get_price(self, product: Product) -> int:
        # Compatibility sentinel only. B03 owns all price authority.
        return 0

    def get_availability(self, product: Product) -> dict[str, Any]:
        return {
            "status": "unknown",
            "authoritative": False,
            "maxQuantity": None,
            "updatedAt": None,
        }

    def get_inStock(self, product: Product) -> bool:
        # Compatibility sentinel only. B03 owns inventory authority.
        return False

    def get_dimensions(self, product: Product) -> dict[str, int | None]:
        return {
            "lensWidthMm": product.lens_width_mm,
            "bridgeWidthMm": product.bridge_width_mm,
            "templeLengthMm": product.temple_length_mm,
            "frameWidthMm": product.frame_width_mm,
        }

    def get_options(self, product: Product) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for option in product.options.all():
            result.append(
                {
                    "key": option.key,
                    "label": option.label,
                    "values": [
                        {
                            "value": value.value,
                            "label": value.label,
                            "available": value.is_active,
                        }
                        for value in option.values.all()
                        if value.is_active
                    ],
                }
            )
        return result

    def get_variants(self, product: Product) -> list[dict[str, Any]]:
        request = self.context.get("request")
        variants: list[dict[str, Any]] = []
        for variant in product.variants.all():
            if not variant.is_active:
                continue
            selections = {
                selection.option.key: selection.value.value
                for selection in variant.option_selections.all()
            }
            variants.append(
                {
                    "id": str(variant.id),
                    "sku": variant.sku,
                    "options": selections,
                    "price": {
                        "current": None,
                        "compareAt": None,
                        "authoritative": False,
                        "source": "backend",
                        "updatedAt": None,
                    },
                    "availability": {
                        "status": "unknown",
                        "authoritative": False,
                        "maxQuantity": None,
                        "updatedAt": None,
                    },
                    "images": [
                        media_payload(media, request)
                        for media in variant.media.all()
                        if media.is_active
                    ],
                }
            )
        return variants

    def get_defaultVariantId(self, product: Product) -> str | None:
        for variant in product.variants.all():
            if variant.is_active and variant.is_default:
                return str(variant.id)
        return None

    def get_badges(self, product: Product) -> list[dict[str, Any]]:
        return [
            {
                "kind": badge.kind,
                "label": badge.label,
                "verified": badge.verified,
            }
            for badge in product.badges.all()
            if badge.is_active
        ]


# These annotations make the nested relations intentionally visible to static readers and docs.
CatalogOptionModel = ProductOption
CatalogVariantModel = ProductVariant
CatalogBadgeModel = ProductBadge
