from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from .models import Room, RoomType, Amenity
from .serializers import RoomSerializer, RoomTypeSerializer, AmenitySerializer


class AmenityViewSet(viewsets.ModelViewSet):
    queryset = Amenity.objects.all()
    serializer_class = AmenitySerializer
    permission_classes = [permissions.IsAuthenticated]


class RoomTypeViewSet(viewsets.ModelViewSet):
    queryset = RoomType.objects.prefetch_related('amenities').all()
    serializer_class = RoomTypeSerializer
    permission_classes = [permissions.IsAuthenticated]


class RoomViewSet(viewsets.ModelViewSet):
    queryset = Room.objects.select_related('room_type').all()
    serializer_class = RoomSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'floor', 'room_type', 'is_active']
    search_fields = ['number']
    ordering_fields = ['number', 'floor']

    @action(detail=False, methods=['get'])
    def available(self, request):
        """Return rooms not occupied during the given check_in/check_out range."""
        check_in = request.query_params.get('check_in')
        check_out = request.query_params.get('check_out')
        qs = self.get_queryset().filter(is_active=True)
        if check_in and check_out:
            from apps.reservations.models import Reservation
            conflicting = Reservation.objects.filter(
                status__in=['confirmed', 'checked_in'],
                check_in__lt=check_out,
                check_out__gt=check_in,
            ).values_list('room_id', flat=True)
            qs = qs.exclude(id__in=conflicting).filter(status='available')
        else:
            qs = qs.filter(status='available')
        serializer = self.get_serializer(qs, many=True)
        return Response(serializer.data)
