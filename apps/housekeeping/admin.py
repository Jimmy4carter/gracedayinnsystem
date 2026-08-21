from django.contrib import admin
from .models import (
    HousekeepingTask, HousekeepingTaskHistory, IncidentReport, IncidentReportHistory,
    LostFoundItem, LostFoundItemHistory, MaintenanceTicket, MaintenanceTicketHistory,
    StockBalance, StockItem, StockLocation, StockMovement,
)
from apps.accounts.admin_permissions import HotelAdminPermissionMixin


@admin.register(HousekeepingTask)
class HousekeepingTaskAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['room', 'task_type', 'priority', 'status', 'assigned_to', 'created_at']
    list_filter = ['status', 'priority', 'task_type']
    search_fields = ['room__number']
    readonly_fields = ['started_at', 'completed_at', 'verified_at', 'verified_by', 'created_at', 'updated_at']


@admin.register(HousekeepingTaskHistory)
class HousekeepingTaskHistoryAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['task', 'action', 'from_status', 'to_status', 'actor', 'created_at']
    readonly_fields = [field.name for field in HousekeepingTaskHistory._meta.fields]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(MaintenanceTicket)
class MaintenanceTicketAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['reference', 'room', 'title', 'priority', 'status', 'downtime_required', 'assigned_to']
    list_filter = ['status', 'priority', 'downtime_required']
    search_fields = ['title', 'description', 'room__number']
    readonly_fields = ['reference', 'status', 'reported_by', 'started_at', 'resolved_at', 'approved_at', 'approved_by']


@admin.register(MaintenanceTicketHistory)
class MaintenanceTicketHistoryAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['ticket', 'action', 'from_status', 'to_status', 'actor', 'created_at']
    readonly_fields = [field.name for field in MaintenanceTicketHistory._meta.fields]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(IncidentReport)
class IncidentReportAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['reference', 'title', 'incident_type', 'severity', 'status', 'assigned_to', 'occurred_at']
    list_filter = ['status', 'severity', 'incident_type']
    search_fields = ['reference', 'title', 'description', 'location']
    readonly_fields = ['reference', 'status', 'reported_by', 'resolution', 'resolved_at', 'closed_at']


@admin.register(IncidentReportHistory)
class IncidentReportHistoryAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['incident', 'action', 'from_status', 'to_status', 'actor', 'created_at']
    readonly_fields = [field.name for field in IncidentReportHistory._meta.fields]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(LostFoundItem)
class LostFoundItemAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['reference', 'item_name', 'status', 'found_location', 'storage_location', 'found_at']
    list_filter = ['status', 'found_at']
    search_fields = ['reference', 'item_name', 'description', 'claimant_name']
    readonly_fields = [field.name for field in LostFoundItem._meta.fields]


@admin.register(LostFoundItemHistory)
class LostFoundItemHistoryAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['item', 'action', 'from_status', 'to_status', 'actor', 'created_at']
    readonly_fields = [field.name for field in LostFoundItemHistory._meta.fields]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(StockLocation)
class StockLocationAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['code', 'name', 'location_type', 'is_active']
    list_filter = ['location_type', 'is_active']


@admin.register(StockItem)
class StockItemAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['sku', 'name', 'category', 'unit', 'reorder_level', 'is_active']
    list_filter = ['category', 'is_active']
    search_fields = ['sku', 'name']


@admin.register(StockBalance)
class StockBalanceAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['item', 'location', 'quantity', 'updated_at']
    list_filter = ['location', 'item__category']
    readonly_fields = [field.name for field in StockBalance._meta.fields]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(StockMovement)
class StockMovementAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['reference', 'item', 'location', 'movement_type', 'quantity_delta', 'resulting_balance', 'actor', 'created_at']
    list_filter = ['movement_type', 'location', 'item__category']
    search_fields = ['reference', 'item__sku', 'item__name', 'reason']
    readonly_fields = [field.name for field in StockMovement._meta.fields]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False
