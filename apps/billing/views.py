from rest_framework import viewsets, permissions
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from .models import Invoice, InvoiceItem, Receipt
from .serializers import InvoiceSerializer, InvoiceItemSerializer, ReceiptSerializer


class InvoiceViewSet(viewsets.ModelViewSet):
    queryset = Invoice.objects.prefetch_related('items').select_related(
        'guest', 'reservation').all()
    serializer_class = InvoiceSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['status', 'guest']
    search_fields = ['invoice_number', 'guest__username']


class InvoiceItemViewSet(viewsets.ModelViewSet):
    queryset = InvoiceItem.objects.select_related('invoice').all()
    serializer_class = InvoiceItemSerializer
    permission_classes = [permissions.IsAuthenticated]


class ReceiptViewSet(viewsets.ModelViewSet):
    queryset = Receipt.objects.select_related('invoice').all()
    serializer_class = ReceiptSerializer
    permission_classes = [permissions.IsAuthenticated]
