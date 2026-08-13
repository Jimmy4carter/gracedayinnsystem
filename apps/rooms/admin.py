from django.contrib import admin
from .models import Amenity, BookableExtra, DailyRate, InventoryBlock, Promotion, RatePlan, Room, RoomType, RoomTypeImage, TaxFee
from apps.accounts.admin_permissions import HotelAdminPermissionMixin


@admin.register(Amenity)
class AmenityAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['name', 'icon']


class RoomTypeImageInline(HotelAdminPermissionMixin, admin.TabularInline):
    model = RoomTypeImage
    extra = 0
    fields = ['image', 'alt_text', 'caption', 'display_order', 'is_featured', 'is_published']


@admin.register(RoomType)
class RoomTypeAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['name', 'base_price', 'max_occupancy']
    filter_horizontal = ['amenities']
    inlines = [RoomTypeImageInline]


@admin.register(RoomTypeImage)
class RoomTypeImageAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['room_type', 'alt_text', 'display_order', 'is_featured', 'is_published', 'updated_at']
    list_filter = ['is_published', 'is_featured', 'room_type']
    list_editable = ['display_order', 'is_published']
    search_fields = ['room_type__name', 'alt_text', 'caption']


@admin.register(Room)
class RoomAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['number', 'room_type', 'floor', 'status', 'is_active', 'is_sellable']
    list_filter = ['status', 'floor', 'room_type', 'is_active', 'is_sellable']
    search_fields = ['number']


class DailyRateInline(HotelAdminPermissionMixin, admin.TabularInline):
    model = DailyRate
    extra = 0


@admin.register(RatePlan)
class RatePlanAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['code', 'name', 'room_type', 'included_adults', 'extra_adult_per_night', 'child_per_night', 'deposit_percent', 'is_active']
    list_filter = ['room_type', 'is_active', 'is_refundable']
    inlines = [DailyRateInline]


@admin.register(TaxFee)
class TaxFeeAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['code', 'name', 'calculation', 'amount', 'is_active']
    list_filter = ['calculation', 'is_active']


@admin.register(Promotion)
class PromotionAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['code', 'name', 'discount_type', 'amount', 'valid_from', 'valid_to', 'times_used', 'is_active']
    list_filter = ['discount_type', 'is_active']
    filter_horizontal = ['room_types']
    readonly_fields = ['times_used', 'created_at']


@admin.register(InventoryBlock)
class InventoryBlockAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['room', 'start_date', 'end_date', 'reason', 'status', 'source_model']
    list_filter = ['status', 'reason', 'start_date']
    readonly_fields = ['status', 'released_by', 'released_at', 'created_by', 'created_at']


@admin.register(BookableExtra)
class BookableExtraAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['code', 'name', 'pricing_model', 'amount', 'taxable', 'is_active']
    list_filter = ['pricing_model', 'taxable', 'is_active']
    filter_horizontal = ['room_types']
