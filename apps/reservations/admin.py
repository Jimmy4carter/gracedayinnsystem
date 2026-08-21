from django.contrib import admin
from .models import (
    BookingQuote, GuestCompanion, GuestConsentHistory, InventoryHold, Reservation,
    ReservationAmendmentHistory, ReservationRoomAssignment, ReservationStatusHistory,
    CorporateAccount, GroupBooking, ReservationDiscountRequest, WaitlistEntry,
)
from apps.accounts.admin_permissions import HotelAdminPermissionMixin


class ReservationStatusHistoryInline(HotelAdminPermissionMixin, admin.TabularInline):
    model = ReservationStatusHistory
    extra = 0
    can_delete = False
    readonly_fields = ['from_status', 'to_status', 'action', 'actor', 'metadata', 'created_at']

    def has_add_permission(self, request, obj=None):
        return False


class ReservationRoomAssignmentInline(HotelAdminPermissionMixin, admin.TabularInline):
    model = ReservationRoomAssignment
    extra = 0
    can_delete = False
    readonly_fields = ['room', 'assigned_by', 'assigned_at', 'released_at', 'reason']

    def has_add_permission(self, request, obj=None):
        return False


class ReservationAmendmentInline(admin.TabularInline):
    model = ReservationAmendmentHistory
    extra = 0
    can_delete = False
    readonly_fields = ['action', 'before', 'after', 'reason', 'actor', 'created_at']

    def has_add_permission(self, request, obj=None): return False


class GuestCompanionInline(admin.TabularInline):
    model = GuestCompanion
    extra = 0


@admin.register(Reservation)
class ReservationAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['reservation_number', 'guest', 'room', 'check_in_date',
                    'check_out_date', 'status', 'total_amount']
    list_filter = ['status']
    search_fields = ['reservation_number', 'guest__username']
    readonly_fields = [
        'reservation_number', 'total_amount', 'status', 'source', 'channel_reference',
        'price_snapshot', 'policy_snapshot', 'room', 'guest', 'check_in_date', 'check_out_date',
        'nightly_rate', 'actual_check_in', 'actual_check_out',
    ]
    inlines = [ReservationStatusHistoryInline, ReservationRoomAssignmentInline, ReservationAmendmentInline, GuestCompanionInline]


class InventoryHoldInline(HotelAdminPermissionMixin, admin.StackedInline):
    model = InventoryHold
    extra = 0
    can_delete = False
    readonly_fields = ['room', 'status', 'expires_at', 'released_at', 'created_at']

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(BookingQuote)
class BookingQuoteAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['reference', 'room', 'rate_plan', 'total', 'status', 'expires_at']
    list_filter = ['status', 'rate_plan']
    readonly_fields = [
        'reference', 'guest', 'email', 'room', 'rate_plan', 'check_in_date', 'check_out_date',
        'num_adults', 'num_children', 'currency', 'subtotal', 'tax_total', 'total',
        'price_snapshot', 'policy_snapshot', 'status', 'expires_at', 'converted_reservation',
        'created_by', 'created_at',
    ]
    inlines = [InventoryHoldInline]


@admin.register(WaitlistEntry)
class WaitlistEntryAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['reference', 'guest', 'room_type', 'check_in_date', 'check_out_date', 'priority', 'status']
    list_filter = ['status', 'room_type']


@admin.register(GuestConsentHistory)
class GuestConsentHistoryAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['guest', 'purpose', 'wording_version', 'granted', 'source', 'created_at']
    readonly_fields = [field.name for field in GuestConsentHistory._meta.fields]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(CorporateAccount)
class CorporateAccountAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['account_code', 'name', 'billing_email', 'credit_limit', 'payment_terms_days', 'status']
    list_filter = ['status']
    search_fields = ['account_code', 'name', 'billing_email']


@admin.register(GroupBooking)
class GroupBookingAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['reference', 'name', 'corporate_account', 'arrival_date', 'departure_date', 'room_target', 'status']
    list_filter = ['status', 'arrival_date']
    search_fields = ['name', 'corporate_account__name']
    readonly_fields = ['reference', 'created_by', 'created_at']


@admin.register(ReservationDiscountRequest)
class ReservationDiscountRequestAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['reservation', 'amount', 'status', 'requested_by', 'reviewed_by', 'requested_at']
    list_filter = ['status', 'requested_at']
    readonly_fields = [field.name for field in ReservationDiscountRequest._meta.fields]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False
