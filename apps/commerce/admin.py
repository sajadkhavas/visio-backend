from django.contrib import admin

from .models import InventoryReservation, VariantInventory, VariantPrice

admin.site.register(VariantPrice)
admin.site.register(VariantInventory)
admin.site.register(InventoryReservation)
