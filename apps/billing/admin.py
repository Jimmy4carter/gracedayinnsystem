from django.contrib import admin
from .models import (
    BankAccount, BankReconciliation, BankStatementLine, FinancialAuditRun,
    FinancialCorrection, Folio, FolioEntry, Invoice, InvoiceItem, JournalEntry,
    JournalLine, LedgerAccount, Receipt, TaxLiability,
)
from apps.accounts.admin_permissions import HotelAdminPermissionMixin


class InvoiceItemInline(HotelAdminPermissionMixin, admin.TabularInline):
    model = InvoiceItem
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['invoice_number', 'guest', 'status', 'total', 'amount_paid', 'balance']
    list_filter = ['status']
    search_fields = ['invoice_number', 'guest__username']
    readonly_fields = ['invoice_number', 'subtotal', 'tax_amount', 'total', 'balance']
    inlines = [InvoiceItemInline]


@admin.register(Receipt)
class ReceiptAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['receipt_number', 'invoice', 'amount', 'issued_at']
    readonly_fields = ['receipt_number']


class FolioEntryInline(admin.TabularInline):
    model = FolioEntry
    extra = 0
    can_delete = False
    readonly_fields = [field.name for field in FolioEntry._meta.fields]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Folio)
class FolioAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['reference', 'reservation', 'guest', 'status', 'debit_total', 'credit_total', 'balance']
    readonly_fields = ['reference', 'reservation', 'guest', 'currency', 'created_at', 'updated_at']
    inlines = [FolioEntryInline]


@admin.register(FolioEntry)
class FolioEntryAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['reference', 'folio', 'direction', 'entry_type', 'amount', 'posted_at']
    readonly_fields = [field.name for field in FolioEntry._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(FinancialCorrection)
class FinancialCorrectionAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ('reference', 'kind', 'folio', 'entry', 'authorized_by', 'created_at')
    readonly_fields = [field.name for field in FinancialCorrection._meta.fields]


    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(LedgerAccount)
class LedgerAccountAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ('code', 'name', 'account_type', 'is_active')
    list_filter = ('account_type', 'is_active')
    search_fields = ('code', 'name')


@admin.register(JournalEntry)
class JournalEntryAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ('reference', 'business_date', 'source_type', 'description', 'posted_at')
    readonly_fields = [field.name for field in JournalEntry._meta.fields]
    inlines = []

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(FinancialAuditRun)
class FinancialAuditRunAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ('period_start', 'period_end', 'run_type', 'status', 'prepared_by', 'approved_by')
    readonly_fields = [field.name for field in FinancialAuditRun._meta.fields]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


class FinanceReadOnlyAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ('__str__',)


for model in (BankAccount, BankReconciliation, BankStatementLine, TaxLiability):
    admin.site.register(model, FinanceReadOnlyAdmin)
