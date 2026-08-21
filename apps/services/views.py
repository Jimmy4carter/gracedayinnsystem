from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.exceptions import ValidationError as ApiValidationError
from django.core.exceptions import ValidationError as DjangoValidationError
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from .models import ServiceCategory, MenuItem, ServiceOrder, ServiceOrderItem
from .serializers import (ServiceCategorySerializer, MenuItemSerializer,
                           ServiceOrderSerializer, ServiceOrderItemSerializer)
from apps.accounts.permissions import RoleActionPermission, has_role
from apps.accounts.api_audit import ApiAuditMixin
from .services import add_service_order_item, remove_service_order_item, transition_service_order

SERVICE_STAFF = {'admin', 'manager', 'receptionist'}
CATALOG_READ = SERVICE_STAFF | {'guest'}


class ServiceCategoryViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = ServiceCategory.objects.all()
    serializer_class = ServiceCategorySerializer
    permission_classes = [RoleActionPermission]
    action_roles = {'list': CATALOG_READ, 'retrieve': CATALOG_READ, 'create': {'admin', 'manager'},
                    'update': {'admin', 'manager'}, 'partial_update': {'admin', 'manager'},
                    'destroy': {'admin', 'manager'}}


class MenuItemViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = MenuItem.objects.select_related('category').all()
    serializer_class = MenuItemSerializer
    permission_classes = [RoleActionPermission]
    action_roles = ServiceCategoryViewSet.action_roles
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['category', 'is_available']
    search_fields = ['name']


class ServiceOrderViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = ServiceOrder.objects.prefetch_related('items').select_related('guest', 'room').all()
    serializer_class = ServiceOrderSerializer
    permission_classes = [RoleActionPermission]
    action_roles = {'list': CATALOG_READ, 'retrieve': CATALOG_READ, 'create': CATALOG_READ,
                    'transition': SERVICE_STAFF, 'add_item': CATALOG_READ, 'remove_item': CATALOG_READ,
                    'update': set(), 'partial_update': set(),
                    'destroy': set()}
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['status', 'guest', 'room']
    search_fields = ['order_number']

    def get_queryset(self):
        queryset = super().get_queryset()
        if has_role(self.request.user, SERVICE_STAFF):
            return queryset
        return queryset.filter(guest=self.request.user)

    def perform_create(self, serializer):
        if has_role(self.request.user, SERVICE_STAFF):
            serializer.save()
        else:
            serializer.save(guest=self.request.user, status='pending')

    @action(detail=True, methods=['post'], url_path='(?P<command>confirm|start|complete|cancel)')
    def transition(self, request, pk=None, command=None):
        try:
            order = transition_service_order(order_id=self.get_object().pk, action=command, actor=request.user)
        except DjangoValidationError as exc:
            raise ApiValidationError(exc.messages)
        return Response(self.get_serializer(order).data)

    @action(detail=True, methods=['post'], url_path='items')
    def add_item(self, request, pk=None):
        try:
            menu_item = MenuItem.objects.get(pk=request.data.get('menu_item'))
            add_service_order_item(
                order_id=self.get_object().pk, menu_item=menu_item,
                quantity=request.data.get('quantity', 1), actor=request.user,
            )
        except (MenuItem.DoesNotExist, DjangoValidationError) as exc:
            raise ApiValidationError(getattr(exc, 'messages', ['Invalid menu item.']))
        return Response(self.get_serializer(self.get_object()).data, status=201)

    @action(detail=True, methods=['post'], url_path='items/(?P<item_id>[^/.]+)/remove')
    def remove_item(self, request, pk=None, item_id=None):
        try:
            remove_service_order_item(
                order_id=self.get_object().pk, item_id=item_id, actor=request.user,
            )
        except DjangoValidationError as exc:
            raise ApiValidationError(exc.messages)
        return Response(self.get_serializer(self.get_object()).data)


class ServiceOrderItemViewSet(ApiAuditMixin, viewsets.ReadOnlyModelViewSet):
    queryset = ServiceOrderItem.objects.select_related('order', 'menu_item').all()
    serializer_class = ServiceOrderItemSerializer
    permission_classes = [RoleActionPermission]
    action_roles = {'list': CATALOG_READ, 'retrieve': CATALOG_READ}

    def get_queryset(self):
        queryset = super().get_queryset()
        if has_role(self.request.user, SERVICE_STAFF):
            return queryset
        return queryset.filter(order__guest=self.request.user)
