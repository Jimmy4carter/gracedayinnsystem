from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CashierShiftViewSet, CashierTerminalViewSet, PaymentViewSet, ReceiptPrintJobViewSet

router = DefaultRouter()
router.register('payments', PaymentViewSet, basename='payment')
router.register('cashier-terminals', CashierTerminalViewSet, basename='cashier-terminal')
router.register('cashier-shifts', CashierShiftViewSet, basename='cashier-shift')
router.register('receipt-print-jobs', ReceiptPrintJobViewSet, basename='receipt-print-job')

urlpatterns = [path('', include(router.urls))]
