from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    BookingQuoteViewSet, CorporateAccountViewSet, GroupBookingViewSet,
    ReservationDiscountRequestViewSet, ReservationViewSet, WaitlistEntryViewSet,
)

router = DefaultRouter()
router.register('reservations', ReservationViewSet, basename='reservation')
router.register('booking-quotes', BookingQuoteViewSet, basename='booking-quote')
router.register('waitlist', WaitlistEntryViewSet, basename='waitlist-entry')
router.register('corporate-accounts', CorporateAccountViewSet, basename='corporate-account')
router.register('group-bookings', GroupBookingViewSet, basename='group-booking')
router.register('discount-requests', ReservationDiscountRequestViewSet, basename='discount-request')

urlpatterns = [path('', include(router.urls))]
