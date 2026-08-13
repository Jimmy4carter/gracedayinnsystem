from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import FolioEntryViewSet, FolioViewSet, InvoiceViewSet, InvoiceItemViewSet, ReceiptViewSet

router = DefaultRouter()
router.register('invoices', InvoiceViewSet, basename='invoice')
router.register('invoice-items', InvoiceItemViewSet, basename='invoice-item')
router.register('receipts', ReceiptViewSet, basename='receipt')
router.register('folios', FolioViewSet, basename='folio')
router.register('folio-entries', FolioEntryViewSet, basename='folio-entry')

urlpatterns = [path('', include(router.urls))]
