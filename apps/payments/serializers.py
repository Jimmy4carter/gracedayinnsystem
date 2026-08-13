from rest_framework import serializers
from .models import (
    CashMovement, CashierShift, CashierTerminal, Payment, PaymentRefund,
    ReceiptPrintJob,
)


class PaymentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Payment
        fields = '__all__'
        read_only_fields = [
            'reference', 'receipt', 'folio', 'status', 'processed_by', 'cashier_shift',
            'created_at', 'updated_at',
        ]


class PaymentRefundSerializer(serializers.ModelSerializer):
    class Meta:
        model = PaymentRefund
        fields = '__all__'
        read_only_fields = ['reference', 'processed_by', 'cashier_shift', 'created_at']


class CashierTerminalSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashierTerminal
        fields = '__all__'
        read_only_fields = ['created_at']


class CashMovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = CashMovement
        fields = '__all__'
        read_only_fields = ['reference', 'recorded_by', 'created_at']


class CashierShiftSerializer(serializers.ModelSerializer):
    cash_movements = CashMovementSerializer(many=True, read_only=True)

    class Meta:
        model = CashierShift
        fields = '__all__'
        read_only_fields = [
            'reference', 'cashier', 'status', 'expected_cash', 'counted_cash',
            'variance', 'opened_at', 'closed_at', 'approved_by', 'close_note',
        ]


class ReceiptPrintJobSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReceiptPrintJob
        fields = '__all__'
        read_only_fields = [
            'reference', 'requested_by', 'status', 'copy_number', 'error_message',
            'attempt_count', 'last_attempt_at', 'completed_by', 'requested_at', 'completed_at',
        ]
