from django.contrib import admin
from .models import ServiceCategory, MenuItem, ServiceOrder, ServiceOrderItem


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'icon']


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = ['name', 'category', 'price', 'is_available']
    list_filter = ['category', 'is_available']


class ServiceOrderItemInline(admin.TabularInline):
    model = ServiceOrderItem
    extra = 0


@admin.register(ServiceOrder)
class ServiceOrderAdmin(admin.ModelAdmin):
    list_display = ['order_number', 'guest', 'room', 'status', 'total']
    list_filter = ['status']
    inlines = [ServiceOrderItemInline]
