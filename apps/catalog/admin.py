from django.contrib import admin

from .models import (
    Brand,
    Category,
    Product,
    ProductBadge,
    ProductMedia,
    ProductOption,
    ProductOptionValue,
    ProductVariant,
    ProductVariantOption,
)

admin.site.register(Brand)
admin.site.register(Category)
admin.site.register(Product)
admin.site.register(ProductOption)
admin.site.register(ProductOptionValue)
admin.site.register(ProductVariant)
admin.site.register(ProductVariantOption)
admin.site.register(ProductMedia)
admin.site.register(ProductBadge)
