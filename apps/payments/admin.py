from django.contrib import admin
from .models import CashMovement, CashierShift, CashierTerminal, Payment, PaymentRefund, ReceiptPrintJob
from apps.accounts.admin_permissions import HotelAdminPermissionMixin


@admin.register(Payment)
class PaymentAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['reference', 'invoice', 'amount', 'method', 'status', 'created_at']
    list_filter = ['status', 'method']
    search_fields = ['reference', 'transaction_id']
    readonly_fields = [
        'reference', 'invoice', 'folio', 'amount', 'method', 'status', 'transaction_id',
        'processed_by', 'cashier_shift', 'idempotency_key', 'created_at', 'updated_at',
    ]


@admin.register(CashierTerminal)
class CashierTerminalAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['code', 'name', 'location', 'receipt_width_mm', 'is_active']


@admin.register(CashierShift)
class CashierShiftAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['reference', 'terminal', 'cashier', 'status', 'expected_cash', 'variance']
    readonly_fields = ['expected_cash', 'variance', 'opened_at', 'closed_at']


@admin.register(CashMovement)
class CashMovementAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['reference', 'shift', 'movement_type', 'amount', 'created_at']
    readonly_fields = [field.name for field in CashMovement._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(PaymentRefund)
class PaymentRefundAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['reference', 'payment', 'amount', 'processed_by', 'created_at']
    readonly_fields = [field.name for field in PaymentRefund._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(ReceiptPrintJob)
class ReceiptPrintJobAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['reference', 'receipt', 'terminal', 'copy_number', 'status', 'attempt_count', 'requested_at']
    readonly_fields = [field.name for field in ReceiptPrintJob._meta.fields]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False
