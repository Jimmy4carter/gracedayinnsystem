from rest_framework import viewsets, permissions
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from .models import ServiceCategory, MenuItem, ServiceOrder, ServiceOrderItem
from .serializers import (ServiceCategorySerializer, MenuItemSerializer,
                           ServiceOrderSerializer, ServiceOrderItemSerializer)


class ServiceCategoryViewSet(viewsets.ModelViewSet):
    queryset = ServiceCategory.objects.all()
    serializer_class = ServiceCategorySerializer
    permission_classes = [permissions.IsAuthenticated]


class MenuItemViewSet(viewsets.ModelViewSet):
    queryset = MenuItem.objects.select_related('category').all()
    serializer_class = MenuItemSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['category', 'is_available']
    search_fields = ['name']


class ServiceOrderViewSet(viewsets.ModelViewSet):
    queryset = ServiceOrder.objects.prefetch_related('items').select_related('guest', 'room').all()
    serializer_class = ServiceOrderSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['status', 'guest', 'room']
    search_fields = ['order_number']

    def perform_create(self, serializer):
        serializer.save(guest=self.request.user)


class ServiceOrderItemViewSet(viewsets.ModelViewSet):
    queryset = ServiceOrderItem.objects.select_related('order', 'menu_item').all()
    serializer_class = ServiceOrderItemSerializer
    permission_classes = [permissions.IsAuthenticated]
