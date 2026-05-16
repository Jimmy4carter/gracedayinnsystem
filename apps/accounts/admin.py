from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import UserProfile, GuestProfile


@admin.register(UserProfile)
class UserProfileAdmin(UserAdmin):
    list_display = ['username', 'email', 'first_name', 'last_name', 'role', 'is_active']
    list_filter = ['role', 'is_active']
    fieldsets = UserAdmin.fieldsets + (
        ('Hotel Profile', {'fields': ('role', 'phone', 'avatar', 'address',
                                      'id_type', 'id_number', 'nationality')}),
    )


@admin.register(GuestProfile)
class GuestProfileAdmin(admin.ModelAdmin):
    list_display = ['user', 'total_stays', 'total_spent', 'created_at']
    search_fields = ['user__username', 'user__email']
