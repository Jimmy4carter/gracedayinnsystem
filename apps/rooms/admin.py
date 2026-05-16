from django.contrib import admin
from .models import Room, RoomType, Amenity


@admin.register(Amenity)
class AmenityAdmin(admin.ModelAdmin):
    list_display = ['name', 'icon']


@admin.register(RoomType)
class RoomTypeAdmin(admin.ModelAdmin):
    list_display = ['name', 'base_price', 'max_occupancy']
    filter_horizontal = ['amenities']


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ['number', 'room_type', 'floor', 'status', 'is_active']
    list_filter = ['status', 'floor', 'room_type', 'is_active']
    search_fields = ['number']
