from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import (
    DataPrivacyRequest, DataPrivacyRequestHistory, GuestMergeHistory, StaffMFADevice,
    UserProfile, GuestProfile,
)
from .admin_permissions import HotelAdminPermissionMixin


@admin.register(UserProfile)
class UserProfileAdmin(HotelAdminPermissionMixin, UserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'role', 'is_active']
    list_filter = ['role', 'is_active']
    readonly_fields = ('merged_into', 'merged_at', 'anonymized_at')
    fieldsets = UserAdmin.fieldsets + (
        ('Hotel Profile', {'fields': ('role', 'phone', 'avatar', 'address',
                                      'id_type', 'id_last_four', 'nationality', 'merged_into', 'merged_at',
                                      'privacy_legal_hold', 'anonymized_at')}),
    )


@admin.register(GuestProfile)
class GuestProfileAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['user', 'total_stays', 'total_spent', 'created_at']
    search_fields = ['user__username', 'user__email']


@admin.register(GuestMergeHistory)
class GuestMergeHistoryAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['duplicate_guest', 'primary_guest', 'merged_by', 'merged_at']
    readonly_fields = [field.name for field in GuestMergeHistory._meta.fields]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(DataPrivacyRequest)
class DataPrivacyRequestAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['reference', 'guest', 'request_type', 'status', 'reviewed_by', 'created_at']
    list_filter = ['request_type', 'status']
    readonly_fields = [field.name for field in DataPrivacyRequest._meta.fields]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(DataPrivacyRequestHistory)
class DataPrivacyRequestHistoryAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['request', 'action', 'from_status', 'to_status', 'actor', 'created_at']
    readonly_fields = [field.name for field in DataPrivacyRequestHistory._meta.fields]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(StaffMFADevice)
class StaffMFADeviceAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['user', 'is_confirmed', 'confirmed_at', 'locked_until', 'updated_at']
    readonly_fields = [field.name for field in StaffMFADevice._meta.fields]
    actions = ['reset_selected_mfa']

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False

    @admin.action(description='Reset selected MFA devices (reason required in audit policy)')
    def reset_selected_mfa(self, request, queryset):
        from .mfa import reset_mfa
        for device in list(queryset.select_related('user')):
            reset_mfa(
                user=device.user, actor=request.user,
                reason='Administrator reset from MFA device administration.',
            )
