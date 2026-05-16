from rest_framework import viewsets, permissions
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
