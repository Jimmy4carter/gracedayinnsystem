from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError as ApiValidationError
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from .models import Folio, FolioEntry, Invoice, InvoiceItem, Receipt
from .serializers import (
    FinancialCorrectionSerializer, FolioEntrySerializer, FolioSerializer, InvoiceSerializer, InvoiceItemSerializer,
    ReceiptSerializer,
)
from .services import post_financial_correction, tax_summary
from apps.accounts.permissions import RoleActionPermission, has_role
from apps.accounts.api_audit import ApiAuditMixin

BILLING_STAFF = {'admin', 'manager', 'receptionist'}
BILLING_READ = BILLING_STAFF | {'guest'}


class BillingScopedMixin:
    permission_classes = [RoleActionPermission]

    def get_queryset(self):
        queryset = super().get_queryset()
        if has_role(self.request.user, BILLING_STAFF):
            return queryset
        return self.scope_to_guest(queryset)


class InvoiceViewSet(ApiAuditMixin, BillingScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Invoice.objects.prefetch_related('items').select_related(
        'guest', 'reservation').all()
    serializer_class = InvoiceSerializer
    action_roles = {'list': BILLING_READ, 'retrieve': BILLING_READ}
    def scope_to_guest(self, queryset):
        return queryset.filter(guest=self.request.user)
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['status', 'guest']
    search_fields = ['invoice_number', 'guest__username']


class InvoiceItemViewSet(ApiAuditMixin, BillingScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = InvoiceItem.objects.select_related('invoice').all()
    serializer_class = InvoiceItemSerializer
    action_roles = InvoiceViewSet.action_roles

    def scope_to_guest(self, queryset):
        return queryset.filter(invoice__guest=self.request.user)


class ReceiptViewSet(ApiAuditMixin, BillingScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Receipt.objects.select_related('invoice').all()
    serializer_class = ReceiptSerializer
    action_roles = InvoiceViewSet.action_roles

    def scope_to_guest(self, queryset):
        return queryset.filter(invoice__guest=self.request.user)


class FolioViewSet(ApiAuditMixin, BillingScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = Folio.objects.select_related('reservation', 'guest').prefetch_related('entries')
    serializer_class = FolioSerializer
    action_roles = {
        'list': BILLING_READ, 'retrieve': BILLING_READ,
        'adjustment': {'admin', 'manager'}, 'credit_note': {'admin', 'manager'},
        'tax_summary': {'admin', 'manager'},
    }

    def scope_to_guest(self, queryset):
        return queryset.filter(guest=self.request.user)

    def _post_correction(self, request, kind):
        try:
            correction = post_financial_correction(
                folio_id=self.get_object().id, kind=kind, amount=request.data.get('amount'),
                reason=request.data.get('reason', ''), actor=request.user,
            )
        except (DjangoValidationError, ValueError, TypeError) as exc:
            raise ApiValidationError(getattr(exc, 'messages', [str(exc)])) from exc
        return Response(FinancialCorrectionSerializer(correction).data, status=201)

    @action(detail=True, methods=['post'])
    def adjustment(self, request, pk=None):
        return self._post_correction(request, 'adjustment')

    @action(detail=True, methods=['post'], url_path='credit-note')
    def credit_note(self, request, pk=None):
        return self._post_correction(request, 'credit_note')

    @action(detail=False, methods=['get'], url_path='tax-summary')
    def tax_summary(self, request):
        summary = tax_summary(
            start_date=request.query_params.get('start_date'),
            end_date=request.query_params.get('end_date'),
        )
        return Response({'rows': summary['rows'], 'total': f"{summary['total']:.2f}"})


class FolioEntryViewSet(BillingScopedMixin, viewsets.ReadOnlyModelViewSet):
    queryset = FolioEntry.objects.select_related('folio', 'posted_by')
    serializer_class = FolioEntrySerializer
    action_roles = {'list': BILLING_READ, 'retrieve': BILLING_READ}

    def scope_to_guest(self, queryset):
        return queryset.filter(folio__guest=self.request.user)
