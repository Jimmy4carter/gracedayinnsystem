from rest_framework import serializers
from .models import FinancialCorrection, Folio, FolioEntry, Invoice, InvoiceItem, Receipt


class InvoiceItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = InvoiceItem
        fields = '__all__'
        read_only_fields = ['total']


class InvoiceSerializer(serializers.ModelSerializer):
    items = InvoiceItemSerializer(many=True, read_only=True)

    class Meta:
        model = Invoice
        fields = '__all__'
        read_only_fields = [
            'invoice_number', 'subtotal', 'tax_rate', 'tax_amount', 'vat_amount',
            'tax_amount_locked', 'total', 'balance',
        ]


class ReceiptSerializer(serializers.ModelSerializer):
    class Meta:
        model = Receipt
        fields = '__all__'
        read_only_fields = ['receipt_number']


class FolioEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = FolioEntry
        fields = '__all__'
        read_only_fields = [field.name for field in FolioEntry._meta.fields]


class FolioSerializer(serializers.ModelSerializer):
    entries = FolioEntrySerializer(many=True, read_only=True)
    debit_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    credit_total = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    balance = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = Folio
        fields = '__all__'
        read_only_fields = [field.name for field in Folio._meta.fields]


class FinancialCorrectionSerializer(serializers.ModelSerializer):
    class Meta:
        model = FinancialCorrection
        fields = '__all__'
        read_only_fields = [field.name for field in FinancialCorrection._meta.fields]
