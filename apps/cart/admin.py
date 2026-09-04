from django.contrib import admin

from .models import Cart, CartLine, WishlistItem

admin.site.register(Cart)
admin.site.register(CartLine)
admin.site.register(WishlistItem)
