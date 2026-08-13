from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    AmenityViewSet, BookableExtraViewSet, DailyRateViewSet, InventoryBlockViewSet,
    RatePlanViewSet, RoomViewSet, RoomTypeViewSet, PromotionViewSet, TaxFeeViewSet,
)

router = DefaultRouter()
router.register('rooms', RoomViewSet, basename='room')
router.register('room-types', RoomTypeViewSet, basename='room-type')
router.register('amenities', AmenityViewSet, basename='amenity')
router.register('rate-plans', RatePlanViewSet, basename='rate-plan')
router.register('daily-rates', DailyRateViewSet, basename='daily-rate')
router.register('tax-fees', TaxFeeViewSet, basename='tax-fee')
router.register('promotions', PromotionViewSet, basename='promotion')
router.register('inventory-blocks', InventoryBlockViewSet, basename='inventory-block')
router.register('bookable-extras', BookableExtraViewSet, basename='bookable-extra')

urlpatterns = [path('', include(router.urls))]
