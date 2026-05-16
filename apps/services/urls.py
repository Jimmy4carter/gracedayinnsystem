from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import ServiceCategoryViewSet, MenuItemViewSet, ServiceOrderViewSet, ServiceOrderItemViewSet

router = DefaultRouter()
router.register('categories', ServiceCategoryViewSet, basename='service-category')
router.register('menu-items', MenuItemViewSet, basename='menu-item')
router.register('orders', ServiceOrderViewSet, basename='service-order')
router.register('order-items', ServiceOrderItemViewSet, basename='service-order-item')

urlpatterns = [path('', include(router.urls))]
