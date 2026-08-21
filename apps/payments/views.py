from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError as ApiValidationError
from django.core.exceptions import ValidationError as DjangoValidationError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from .models import CashierShift, CashierTerminal, Payment, ReceiptPrintJob
from .serializers import (
    CashierShiftSerializer, CashierTerminalSerializer, PaymentRefundSerializer,
    PaymentSerializer, ReceiptPrintJobSerializer,
)
from .services import (
    cashier_shift_summary, close_cashier_shift, open_cashier_shift,
    record_manual_cash_movement, record_payment, record_print_result, refund_payment,
    request_receipt_print, retry_print_job,
)
from apps.accounts.permissions import RoleActionPermission, has_role
from apps.accounts.api_audit import ApiAuditMixin

PAYMENT_STAFF = {'admin', 'manager', 'receptionist'}


class PaymentViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = Payment.objects.select_related(
        'invoice', 'receipt', 'folio', 'processed_by', 'cashier_shift'
    ).all()
    serializer_class = PaymentSerializer
    permission_classes = [RoleActionPermission]
    action_roles = {'list': PAYMENT_STAFF | {'guest'}, 'retrieve': PAYMENT_STAFF | {'guest'},
                    'create': PAYMENT_STAFF, 'refund': {'admin', 'manager'},
                    'update': set(), 'partial_update': set(), 'destroy': set()}
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['status', 'method', 'invoice']
    search_fields = ['reference', 'transaction_id']

    def get_queryset(self):
        queryset = super().get_queryset()
        if has_role(self.request.user, PAYMENT_STAFF):
            return queryset
        return queryset.filter(invoice__guest=self.request.user)

    def perform_create(self, serializer):
        data = serializer.validated_data
        try:
            payment, _, _ = record_payment(
                invoice=data['invoice'], amount=data['amount'], method=data['method'],
                actor=self.request.user, idempotency_key=data.get('idempotency_key'),
                transaction_id=data.get('transaction_id', ''), notes=data.get('notes', ''),
            )
            serializer.instance = payment
        except DjangoValidationError as exc:
            raise ApiValidationError(exc.messages)

    @action(detail=True, methods=['post'])
    def refund(self, request, pk=None):
        payment = self.get_object()
        serializer = PaymentRefundSerializer(data={**request.data, 'payment': payment.id})
        serializer.is_valid(raise_exception=True)
        try:
            refund, _ = refund_payment(
                payment=payment, amount=serializer.validated_data['amount'],
                reason=serializer.validated_data['reason'], actor=request.user,
                idempotency_key=serializer.validated_data['idempotency_key'],
            )
        except DjangoValidationError as exc:
            raise ApiValidationError(exc.messages)
        return Response(PaymentRefundSerializer(refund).data, status=status.HTTP_201_CREATED)


class CashierTerminalViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = CashierTerminal.objects.all()
    serializer_class = CashierTerminalSerializer
    permission_classes = [RoleActionPermission]
    action_roles = {
        'list': PAYMENT_STAFF, 'retrieve': PAYMENT_STAFF,
        'create': {'admin', 'manager'}, 'update': {'admin', 'manager'},
        'partial_update': {'admin', 'manager'}, 'destroy': {'admin'},
    }


class CashierShiftViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = CashierShift.objects.select_related(
        'terminal', 'cashier', 'approved_by'
    ).prefetch_related('cash_movements').all()
    serializer_class = CashierShiftSerializer
    permission_classes = [RoleActionPermission]
    action_roles = {
        'list': PAYMENT_STAFF, 'retrieve': PAYMENT_STAFF, 'create': PAYMENT_STAFF,
        'close': PAYMENT_STAFF, 'report': PAYMENT_STAFF,
        'cash_movement': {'admin', 'manager'},
        'update': set(), 'partial_update': set(), 'destroy': set(),
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        if has_role(self.request.user, {'admin', 'manager'}):
            return queryset
        return queryset.filter(cashier=self.request.user)

    def perform_create(self, serializer):
        try:
            serializer.instance = open_cashier_shift(
                terminal=serializer.validated_data['terminal'], cashier=self.request.user,
                opening_float=serializer.validated_data.get('opening_float', 0),
            )
        except DjangoValidationError as exc:
            raise ApiValidationError(exc.messages)

    @action(detail=True, methods=['post'])
    def close(self, request, pk=None):
        shift = self.get_object()
        try:
            shift = close_cashier_shift(
                shift=shift, counted_cash=request.data.get('counted_cash'),
                actor=request.user, note=request.data.get('note', ''),
            )
        except (DjangoValidationError, TypeError) as exc:
            messages = getattr(exc, 'messages', ['A valid counted cash amount is required.'])
            raise ApiValidationError(messages)
        return Response(self.get_serializer(shift).data)

    @action(detail=True, methods=['get'])
    def report(self, request, pk=None):
        return Response(cashier_shift_summary(self.get_object()))

    @action(detail=True, methods=['post'], url_path='cash-movement')
    def cash_movement(self, request, pk=None):
        try:
            movement, created = record_manual_cash_movement(
                shift=self.get_object(), movement_type=request.data.get('movement_type'),
                amount=request.data.get('amount'), actor=request.user,
                notes=request.data.get('notes', ''),
                idempotency_key=request.data.get('idempotency_key'),
            )
        except (DjangoValidationError, TypeError) as exc:
            raise ApiValidationError(getattr(exc, 'messages', [str(exc)]))
        from .serializers import CashMovementSerializer
        return Response(
            CashMovementSerializer(movement).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class ReceiptPrintJobViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = ReceiptPrintJob.objects.select_related(
        'receipt', 'terminal', 'requested_by'
    ).all()
    serializer_class = ReceiptPrintJobSerializer
    permission_classes = [RoleActionPermission]
    action_roles = {
        'list': PAYMENT_STAFF, 'retrieve': PAYMENT_STAFF, 'create': PAYMENT_STAFF,
        'printed': PAYMENT_STAFF, 'failed': PAYMENT_STAFF, 'retry': PAYMENT_STAFF,
        'update': set(), 'partial_update': set(), 'destroy': set(),
    }

    def perform_create(self, serializer):
        serializer.instance = request_receipt_print(
            receipt=serializer.validated_data['receipt'],
            terminal=serializer.validated_data['terminal'], actor=self.request.user,
        )

    @action(detail=True, methods=['post'])
    def printed(self, request, pk=None):
        try:
            job = record_print_result(job=self.get_object(), success=True, actor=request.user)
        except DjangoValidationError as exc:
            raise ApiValidationError(exc.messages)
        return Response(self.get_serializer(job).data)

    @action(detail=True, methods=['post'])
    def failed(self, request, pk=None):
        try:
            job = record_print_result(
                job=self.get_object(), success=False, actor=request.user,
                error_message=request.data.get('error_message', ''),
            )
        except DjangoValidationError as exc:
            raise ApiValidationError(exc.messages)
        return Response(self.get_serializer(job).data)

    @action(detail=True, methods=['post'])
    def retry(self, request, pk=None):
        try:
            job = retry_print_job(job=self.get_object(), actor=request.user)
        except DjangoValidationError as exc:
            raise ApiValidationError(exc.messages)
        return Response(self.get_serializer(job).data)
