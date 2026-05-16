from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.utils import timezone
from .models import Reservation
from .serializers import ReservationSerializer


class ReservationViewSet(viewsets.ModelViewSet):
    queryset = Reservation.objects.select_related('guest', 'room', 'room__room_type').all()
    serializer_class = ReservationSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'room', 'guest']
    search_fields = ['reservation_number', 'guest__username', 'guest__email']
    ordering_fields = ['check_in_date', 'check_out_date', 'created_at']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def check_in(self, request, pk=None):
        reservation = self.get_object()
        if reservation.status != 'confirmed':
            return Response({'error': 'Only confirmed reservations can be checked in.'},
                            status=status.HTTP_400_BAD_REQUEST)
        reservation.status = 'checked_in'
        reservation.actual_check_in = timezone.now()
        reservation.room.status = 'occupied'
        reservation.room.save()
        reservation.save()
        return Response(ReservationSerializer(reservation).data)

    @action(detail=True, methods=['post'])
    def check_out(self, request, pk=None):
        reservation = self.get_object()
        if reservation.status != 'checked_in':
            return Response({'error': 'Only checked-in reservations can be checked out.'},
                            status=status.HTTP_400_BAD_REQUEST)
        reservation.status = 'checked_out'
        reservation.actual_check_out = timezone.now()
        reservation.room.status = 'housekeeping'
        reservation.room.save()
        reservation.save()
        return Response(ReservationSerializer(reservation).data)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        reservation = self.get_object()
        if reservation.status != 'pending':
            return Response({'error': 'Only pending reservations can be confirmed.'},
                            status=status.HTTP_400_BAD_REQUEST)
        reservation.status = 'confirmed'
        reservation.save()
        return Response(ReservationSerializer(reservation).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        reservation = self.get_object()
        if reservation.status in ('checked_in', 'checked_out'):
            return Response({'error': 'Cannot cancel this reservation.'},
                            status=status.HTTP_400_BAD_REQUEST)
        reservation.status = 'cancelled'
        reservation.save()
        return Response(ReservationSerializer(reservation).data)
