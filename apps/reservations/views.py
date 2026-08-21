from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.exceptions import ValidationError as ApiValidationError
from .models import BookingQuote, CorporateAccount, GroupBooking, Reservation, ReservationDiscountRequest, WaitlistEntry
from .serializers import (
    BookingQuoteSerializer, CorporateAccountSerializer, GroupBookingSerializer,
    ReservationDiscountRequestSerializer, ReservationSerializer, WaitlistEntrySerializer,
)
from apps.accounts.permissions import RoleActionPermission, has_role
from apps.accounts.api_audit import ApiAuditMixin
from .services import (
    amend_reservation_stay, convert_waitlist_entry, create_reservation,
    move_reservation_room, offer_waitlist_entry, request_reservation_discount,
    review_reservation_discount, transition_reservation,
)
from apps.rooms.models import Room
from django.utils.dateparse import parse_date
from .pricing import convert_quote, create_quote

RESERVATION_STAFF = {'admin', 'manager', 'receptionist'}


class ReservationViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = Reservation.objects.select_related('guest', 'room', 'room__room_type').all()
    serializer_class = ReservationSerializer
    permission_classes = [RoleActionPermission]
    action_roles = {
        'list': RESERVATION_STAFF | {'guest'}, 'retrieve': RESERVATION_STAFF | {'guest'},
        'create': RESERVATION_STAFF | {'guest'}, 'update': set(),
        'partial_update': set(), 'destroy': set(),
        'check_in': RESERVATION_STAFF, 'check_out': RESERVATION_STAFF,
        'confirm': RESERVATION_STAFF, 'cancel': RESERVATION_STAFF | {'guest'},
        'move_room': RESERVATION_STAFF, 'amend': RESERVATION_STAFF,
    }
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['status', 'room', 'guest']
    search_fields = ['reservation_number', 'guest__username', 'guest__email']
    ordering_fields = ['check_in_date', 'check_out_date', 'created_at']

    def get_queryset(self):
        queryset = super().get_queryset()
        if has_role(self.request.user, RESERVATION_STAFF):
            return queryset
        return queryset.filter(guest=self.request.user)

    def perform_create(self, serializer):
        data = serializer.validated_data
        guest = data.get('guest') if has_role(self.request.user, RESERVATION_STAFF) else self.request.user
        try:
            serializer.instance = create_reservation(
                guest=guest,
                room=data['room'],
                check_in_date=data['check_in_date'],
                check_out_date=data['check_out_date'],
                num_adults=data.get('num_adults', 1),
                num_children=data.get('num_children', 0),
                special_requests=data.get('special_requests', ''),
                notes=data.get('notes', ''),
                created_by=self.request.user,
                source='api',
                corporate_account=data.get('corporate_account') if has_role(self.request.user, RESERVATION_STAFF) else None,
                group_booking=data.get('group_booking') if has_role(self.request.user, RESERVATION_STAFF) else None,
            )
        except DjangoValidationError as exc:
            raise ApiValidationError(getattr(exc, 'message_dict', exc.messages))

    def _transition(self, request, action):
        scoped = self.get_object()
        try:
            reservation = transition_reservation(
                reservation_id=scoped.pk, action=action, actor=request.user
            )
        except DjangoValidationError as exc:
            return Response(
                {'error': '; '.join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST
            )
        return Response(ReservationSerializer(reservation).data)

    @action(detail=True, methods=['post'])
    def check_in(self, request, pk=None):
        return self._transition(request, 'check_in')

    @action(detail=True, methods=['post'])
    def check_out(self, request, pk=None):
        return self._transition(request, 'check_out')

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        return self._transition(request, 'confirm')

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        return self._transition(request, 'cancel')

    @action(detail=True, methods=['post'], url_path='move-room')
    def move_room(self, request, pk=None):
        try:
            room = Room.objects.get(pk=request.data.get('room'))
            reservation = move_reservation_room(
                reservation_id=self.get_object().pk, new_room=room, actor=request.user,
                reason=request.data.get('reason', 'Room move'),
            )
        except (Room.DoesNotExist, DjangoValidationError) as exc:
            raise ApiValidationError(getattr(exc, 'messages', ['Invalid room.']))
        return Response(self.get_serializer(reservation).data)

    @action(detail=True, methods=['post'])
    def amend(self, request, pk=None):
        current = self.get_object()
        try:
            reservation = amend_reservation_stay(
                reservation_id=current.pk,
                check_in_date=parse_date(request.data.get('check_in_date', '')),
                check_out_date=parse_date(request.data.get('check_out_date', '')),
                num_adults=int(request.data.get('num_adults', current.num_adults)),
                num_children=int(request.data.get('num_children', current.num_children)),
                actor=request.user, reason=request.data.get('reason', 'Stay amendment'),
            )
        except (DjangoValidationError, TypeError, ValueError) as exc:
            raise ApiValidationError(getattr(exc, 'messages', ['Invalid amendment data.']))
        return Response(self.get_serializer(reservation).data)


class BookingQuoteViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = BookingQuote.objects.select_related(
        'guest', 'room', 'room__room_type', 'rate_plan', 'converted_reservation'
    ).all()
    serializer_class = BookingQuoteSerializer
    permission_classes = [RoleActionPermission]
    action_roles = {
        'list': RESERVATION_STAFF | {'guest'},
        'retrieve': RESERVATION_STAFF | {'guest'},
        'create': RESERVATION_STAFF | {'guest'},
        'convert': RESERVATION_STAFF | {'guest'},
        'update': set(), 'partial_update': set(), 'destroy': set(),
    }

    def get_queryset(self):
        queryset = super().get_queryset()
        if has_role(self.request.user, RESERVATION_STAFF):
            return queryset
        return queryset.filter(guest=self.request.user)

    def perform_create(self, serializer):
        data = serializer.validated_data
        guest = data.get('guest') if has_role(self.request.user, RESERVATION_STAFF) else self.request.user
        try:
            serializer.instance = create_quote(
                guest=guest, email=(data.get('email', '') if has_role(self.request.user, RESERVATION_STAFF) else guest.email), room=data['room'],
                rate_plan=data['rate_plan'], check_in_date=data['check_in_date'],
                check_out_date=data['check_out_date'], num_adults=data.get('num_adults', 1),
                num_children=data.get('num_children', 0), created_by=self.request.user,
                promotion_code=data.get('promotion_code', ''),
                extras=data.get('extras', []),
            )
        except DjangoValidationError as exc:
            raise ApiValidationError(getattr(exc, 'message_dict', exc.messages))

    @action(detail=True, methods=['post'])
    def convert(self, request, pk=None):
        quote = self.get_object()
        guest = quote.guest or request.user
        try:
            reservation = convert_quote(
                quote_id=quote.id, guest=guest, created_by=request.user, source='api'
            )
        except DjangoValidationError as exc:
            return Response({'error': '; '.join(exc.messages)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(ReservationSerializer(reservation).data, status=status.HTTP_201_CREATED)


class WaitlistEntryViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = WaitlistEntry.objects.select_related('guest', 'room_type', 'converted_reservation')
    serializer_class = WaitlistEntrySerializer
    permission_classes = [RoleActionPermission]
    action_roles = {
        'list': RESERVATION_STAFF, 'retrieve': RESERVATION_STAFF,
        'create': RESERVATION_STAFF, 'offer': RESERVATION_STAFF,
        'convert': RESERVATION_STAFF, 'update': set(), 'partial_update': set(), 'destroy': set(),
    }

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def offer(self, request, pk=None):
        try:
            entry = offer_waitlist_entry(entry_id=self.get_object().pk, actor=request.user)
        except DjangoValidationError as exc:
            raise ApiValidationError(exc.messages)
        return Response(self.get_serializer(entry).data)

    @action(detail=True, methods=['post'])
    def convert(self, request, pk=None):
        try:
            room = Room.objects.get(pk=request.data.get('room'))
            reservation = convert_waitlist_entry(
                entry_id=self.get_object().pk, room=room, actor=request.user
            )
        except (Room.DoesNotExist, DjangoValidationError) as exc:
            raise ApiValidationError(getattr(exc, 'messages', ['Invalid room.']))
        return Response(ReservationSerializer(reservation).data, status=status.HTTP_201_CREATED)


class CorporateAccountViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = CorporateAccount.objects.all()
    serializer_class = CorporateAccountSerializer
    permission_classes = [RoleActionPermission]
    action_roles = {
        'list': RESERVATION_STAFF, 'retrieve': RESERVATION_STAFF,
        'create': {'admin', 'manager'}, 'update': {'admin', 'manager'},
        'partial_update': {'admin', 'manager'}, 'destroy': set(),
    }
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['status']
    search_fields = ['name', 'account_code', 'billing_email']


class GroupBookingViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = GroupBooking.objects.select_related('corporate_account', 'created_by').all()
    serializer_class = GroupBookingSerializer
    permission_classes = [RoleActionPermission]
    action_roles = {
        'list': RESERVATION_STAFF, 'retrieve': RESERVATION_STAFF,
        'create': RESERVATION_STAFF, 'update': RESERVATION_STAFF,
        'partial_update': RESERVATION_STAFF, 'destroy': set(),
    }
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['status', 'corporate_account', 'arrival_date']
    search_fields = ['name', 'corporate_account__name']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


class ReservationDiscountRequestViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = ReservationDiscountRequest.objects.select_related('reservation', 'requested_by', 'reviewed_by')
    serializer_class = ReservationDiscountRequestSerializer
    permission_classes = [RoleActionPermission]
    action_roles = {
        'list': RESERVATION_STAFF, 'retrieve': RESERVATION_STAFF,
        'create': RESERVATION_STAFF, 'approve': {'admin', 'manager'},
        'reject': {'admin', 'manager'}, 'update': set(), 'partial_update': set(), 'destroy': set(),
    }
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['reservation', 'status', 'requested_by']

    def perform_create(self, serializer):
        data = serializer.validated_data
        try:
            serializer.instance = request_reservation_discount(
                reservation_id=data['reservation'].id, amount=data['amount'],
                reason=data['reason'], actor=self.request.user,
            )
        except DjangoValidationError as exc:
            raise ApiValidationError(exc.messages)

    def _review(self, request, action):
        try:
            discount = review_reservation_discount(
                request_id=self.get_object().id, action=action, actor=request.user,
                note=request.data.get('note', ''),
            )
        except DjangoValidationError as exc:
            raise ApiValidationError(exc.messages)
        return Response(self.get_serializer(discount).data)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None): return self._review(request, 'approve')

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None): return self._review(request, 'reject')
