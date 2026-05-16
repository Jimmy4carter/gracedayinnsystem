from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ServiceCategoryViewSet, MenuItemViewSet, ServiceOrderViewSet, ServiceOrderItemViewSet

router = DefaultRouter()
router.register('service-categories', ServiceCategoryViewSet, basename='service-category')
router.register('restaurant-menu', MenuItemViewSet, basename='restaurant-menu')
router.register('service-orders', ServiceOrderViewSet, basename='service-order')
router.register('service-order-items', ServiceOrderItemViewSet, basename='service-order-item')

urlpatterns = [path('', include(router.urls))]
