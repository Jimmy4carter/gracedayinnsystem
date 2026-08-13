from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import Amenity, BookableExtra, DailyRate, InventoryBlock, Promotion, RatePlan, Room, RoomType, TaxFee
from .serializers import (
    AmenitySerializer, DailyRateSerializer, RatePlanSerializer, RoomSerializer,
    BookableExtraSerializer, InventoryBlockSerializer, PromotionSerializer,
    RoomTypeSerializer, TaxFeeSerializer,
)
from apps.accounts.permissions import RoleActionPermission
from apps.accounts.api_audit import ApiAuditMixin

CATALOG_READ_ROLES = {'admin', 'manager', 'receptionist', 'housekeeping', 'guest'}
CATALOG_MANAGE_ROLES = {'admin', 'manager'}


class AmenityViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = Amenity.objects.all()
    serializer_class = AmenitySerializer
    permission_classes = [RoleActionPermission]
    action_roles = {'list': CATALOG_READ_ROLES, 'retrieve': CATALOG_READ_ROLES,
                    'create': CATALOG_MANAGE_ROLES, 'update': CATALOG_MANAGE_ROLES,
                    'partial_update': CATALOG_MANAGE_ROLES, 'destroy': CATALOG_MANAGE_ROLES}


class RoomTypeViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = RoomType.objects.prefetch_related('amenities', 'gallery_images').order_by('name', 'id')
    serializer_class = RoomTypeSerializer
    permission_classes = [RoleActionPermission]
    action_roles = AmenityViewSet.action_roles


class RoomViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = Room.objects.select_related('room_type').all()
    serializer_class = RoomSerializer
    permission_classes = [RoleActionPermission]
    action_roles = {**AmenityViewSet.action_roles, 'available': CATALOG_READ_ROLES}
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'floor', 'room_type', 'is_active']
    search_fields = ['number']
    ordering_fields = ['number', 'floor']

    @action(detail=False, methods=['get'])
    def available(self, request):
        """Return rooms not occupied during the given check_in/check_out range."""
        check_in = request.query_params.get('check_in')
        check_out = request.query_params.get('check_out')
        qs = self.get_queryset().filter(is_active=True, is_sellable=True)
        if check_in and check_out:
            from django.utils import timezone
            from apps.reservations.models import InventoryHold, Reservation
            conflicting = Reservation.objects.filter(
                status__in=['pending', 'confirmed', 'checked_in'],
                check_in_date__lt=check_out,
                check_out_date__gt=check_in,
            ).values_list('room_id', flat=True)
            qs = qs.exclude(id__in=conflicting).filter(status='available')
            held = InventoryHold.objects.filter(
                status='active', expires_at__gt=timezone.now(),
                quote__check_in_date__lt=check_out,
                quote__check_out_date__gt=check_in,
            ).values_list('room_id', flat=True)
            qs = qs.exclude(id__in=held)
            blocked = InventoryBlock.objects.filter(
                status='active', start_date__lt=check_out, end_date__gt=check_in,
            ).values_list('room_id', flat=True)
            qs = qs.exclude(id__in=blocked)
        else:
            qs = qs.filter(status='available')
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)


class RatePlanViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = RatePlan.objects.select_related('room_type').prefetch_related('daily_rates').all()
    serializer_class = RatePlanSerializer
    permission_classes = [RoleActionPermission]
    action_roles = AmenityViewSet.action_roles
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['room_type', 'is_active', 'is_refundable']
    search_fields = ['name', 'code']


class DailyRateViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = DailyRate.objects.select_related('rate_plan').all()
    serializer_class = DailyRateSerializer
    permission_classes = [RoleActionPermission]
    action_roles = AmenityViewSet.action_roles
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['rate_plan', 'date']


class TaxFeeViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = TaxFee.objects.all()
    serializer_class = TaxFeeSerializer
    permission_classes = [RoleActionPermission]
    action_roles = AmenityViewSet.action_roles
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['is_active', 'calculation']


class PromotionViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = Promotion.objects.prefetch_related('room_types').all()
    serializer_class = PromotionSerializer
    permission_classes = [RoleActionPermission]
    action_roles = AmenityViewSet.action_roles
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['is_active', 'discount_type']
    search_fields = ['code', 'name']


class InventoryBlockViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = InventoryBlock.objects.select_related('room', 'created_by', 'released_by')
    serializer_class = InventoryBlockSerializer
    permission_classes = [RoleActionPermission]
    action_roles = {
        'list': CATALOG_MANAGE_ROLES | {'receptionist'}, 'retrieve': CATALOG_MANAGE_ROLES | {'receptionist'},
        'create': CATALOG_MANAGE_ROLES, 'release': CATALOG_MANAGE_ROLES,
        'update': set(), 'partial_update': set(), 'destroy': set(),
    }
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['room', 'status', 'reason', 'start_date']

    def perform_create(self, serializer):
        from .inventory import create_inventory_block
        data = serializer.validated_data
        serializer.instance = create_inventory_block(
            room=data['room'], start_date=data['start_date'], end_date=data['end_date'],
            reason=data['reason'], notes=data.get('notes', ''), actor=self.request.user,
            source_model='api',
        )

    @action(detail=True, methods=['post'])
    def release(self, request, pk=None):
        from .inventory import release_inventory_block
        block = release_inventory_block(block_id=self.get_object().id, actor=request.user)
        return Response(self.get_serializer(block).data)


class BookableExtraViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = BookableExtra.objects.prefetch_related('room_types')
    serializer_class = BookableExtraSerializer
    permission_classes = [RoleActionPermission]
    action_roles = AmenityViewSet.action_roles
