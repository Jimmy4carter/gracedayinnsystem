from django.contrib import admin
from .models import Invoice, InvoiceItem, Receipt


class InvoiceItemInline(admin.TabularInline):
    model = InvoiceItem
    extra = 0


@admin.register(Invoice)
class InvoiceAdmin(admin.ModelAdmin):
    list_display = ['invoice_number', 'guest', 'status', 'total', 'amount_paid', 'balance']
    list_filter = ['status']
    search_fields = ['invoice_number', 'guest__username']
    readonly_fields = ['invoice_number', 'subtotal', 'tax_amount', 'total', 'balance']
    inlines = [InvoiceItemInline]


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ['receipt_number', 'invoice', 'amount', 'issued_at']
    readonly_fields = ['receipt_number']
