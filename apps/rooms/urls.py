from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import RoomViewSet, RoomTypeViewSet, AmenityViewSet

router = DefaultRouter()
router.register('rooms', RoomViewSet, basename='room')
router.register('room-types', RoomTypeViewSet, basename='room-type')
router.register('amenities', AmenityViewSet, basename='amenity')

urlpatterns = [path('', include(router.urls))]
