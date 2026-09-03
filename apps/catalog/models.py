from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.functions import Lower


class Brand(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=160, unique=True, allow_unicode=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "name", "id")

    def __str__(self) -> str:
        return self.name


class Category(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=160, unique=True, allow_unicode=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="children",
    )
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "name", "id")
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(parent=models.F("id")),
                name="catalog_category_not_self",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.parent_id is None:
            return
        if self.parent_id == self.id:
            raise ValidationError({"parent": "A category cannot be its own parent."})

        ancestor = self.parent
        visited = {self.id}
        while ancestor is not None:
            if ancestor.id in visited:
                raise ValidationError({"parent": "Category hierarchy cannot contain a cycle."})
            visited.add(ancestor.id)
            ancestor = ancestor.parent

    def __str__(self) -> str:
        return self.name


class Product(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        PUBLISHED = "published", "Published"
        ARCHIVED = "archived", "Archived"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    slug = models.SlugField(max_length=180, unique=True, allow_unicode=True)
    name = models.CharField(max_length=220)
    brand = models.ForeignKey(Brand, on_delete=models.PROTECT, related_name="products")
    category = models.ForeignKey(Category, on_delete=models.PROTECT, related_name="products")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.DRAFT)
    published_at = models.DateTimeField(null=True, blank=True)
    shape = models.CharField(max_length=120, blank=True)
    material = models.CharField(max_length=120, blank=True)
    color = models.CharField(max_length=120, blank=True)
    lens_width_mm = models.PositiveSmallIntegerField(null=True, blank=True)
    bridge_width_mm = models.PositiveSmallIntegerField(null=True, blank=True)
    temple_length_mm = models.PositiveSmallIntegerField(null=True, blank=True)
    frame_width_mm = models.PositiveSmallIntegerField(null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "name", "id")
        indexes = [
            models.Index(
                fields=("status", "published_at", "sort_order"),
                name="catalog_prod_public_idx",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(~models.Q(status="published") | models.Q(published_at__isnull=False)),
                name="catalog_prod_publish_time",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class ProductOption(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="options")
    key = models.SlugField(max_length=80, allow_unicode=True)
    label = models.CharField(max_length=120)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("product", "key"),
                name="catalog_option_product_key_uq",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.product}: {self.label}"


class ProductOptionValue(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    option = models.ForeignKey(ProductOption, on_delete=models.CASCADE, related_name="values")
    value = models.CharField(max_length=100)
    label = models.CharField(max_length=120)
    is_active = models.BooleanField(default=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("option", "value"),
                name="catalog_opt_value_unique",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.option}: {self.label}"


class ProductVariant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="variants")
    sku = models.CharField(max_length=120, null=True, blank=True)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    sort_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("sort_order", "id")
        constraints = [
            models.UniqueConstraint(
                Lower("sku"),
                condition=models.Q(sku__isnull=False) & ~models.Q(sku=""),
                name="catalog_variant_sku_ci_uq",
            ),
            models.UniqueConstraint(
                fields=("product",),
                condition=models.Q(is_default=True),
                name="catalog_one_default_variant",
            ),
        ]

    def __str__(self) -> str:
        return self.sku or str(self.id)


class ProductVariantOption(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        related_name="option_selections",
    )
    option = models.ForeignKey(
        ProductOption, on_delete=models.PROTECT, related_name="variant_selections"
    )
    value = models.ForeignKey(
        ProductOptionValue,
        on_delete=models.PROTECT,
        related_name="variant_selections",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=("variant", "option"),
                name="catalog_variant_option_uq",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.option_id is not None and self.variant_id is not None:
            if self.option.product_id != self.variant.product_id:
                errors["option"] = "Variant and option must belong to the same product."
        if self.value_id is not None and self.option_id is not None:
            if self.value.option_id != self.option_id:
                errors["value"] = "Selected value must belong to the selected option."
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return f"{self.variant}: {self.option.key}={self.value.value}"


def catalog_media_upload_to(instance: ProductMedia, filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    return f"catalog/{instance.product_id}/{instance.id}{suffix}"


class ProductMedia(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="media")
    variant = models.ForeignKey(
        ProductVariant,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="media",
    )
    file = models.FileField(upload_to=catalog_media_upload_to, max_length=500)
    alt = models.CharField(max_length=255)
    width = models.PositiveIntegerField(null=True, blank=True)
    height = models.PositiveIntegerField(null=True, blank=True)
    position = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("product", "position"),
                condition=models.Q(variant__isnull=True),
                name="catalog_product_media_pos_uq",
            ),
            models.UniqueConstraint(
                fields=("variant", "position"),
                condition=models.Q(variant__isnull=False),
                name="catalog_variant_media_pos_uq",
            ),
        ]

    def clean(self) -> None:
        super().clean()
        if self.variant_id is not None and self.variant.product_id != self.product_id:
            raise ValidationError({"variant": "Media variant must belong to the same product."})

    def __str__(self) -> str:
        return self.alt


class ProductBadge(models.Model):
    class Kind(models.TextChoices):
        NEW = "new", "New"
        LIMITED = "limited", "Limited"
        EDITORIAL = "editorial", "Editorial"

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="badges")
    kind = models.CharField(max_length=16, choices=Kind.choices)
    label = models.CharField(max_length=120)
    verified = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)
    position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ("position", "id")
        constraints = [
            models.UniqueConstraint(
                fields=("product", "kind", "label"),
                name="catalog_badge_identity_uq",
            ),
        ]

    def __str__(self) -> str:
        return self.label
