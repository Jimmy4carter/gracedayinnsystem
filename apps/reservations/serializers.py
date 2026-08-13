from rest_framework import serializers
from .models import (
    BookingQuote, CorporateAccount, GroupBooking, GuestCompanion, Reservation, ReservationAmendmentHistory,
    ReservationDiscountRequest,
    ReservationRoomAssignment, ReservationStatusHistory, WaitlistEntry,
)
from apps.rooms.serializers import RoomSerializer
from apps.rooms.models import BookableExtra
from apps.accounts.serializers import UserProfileSerializer


class ReservationStatusHistorySerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source='actor.username', read_only=True)

    class Meta:
        model = ReservationStatusHistory
        fields = ['id', 'from_status', 'to_status', 'action', 'actor', 'actor_name', 'metadata', 'created_at']
        read_only_fields = fields


class ReservationRoomAssignmentSerializer(serializers.ModelSerializer):
    room_number = serializers.CharField(source='room.number', read_only=True)

    class Meta:
        model = ReservationRoomAssignment
        fields = ['id', 'room', 'room_number', 'assigned_by', 'assigned_at', 'released_at', 'reason']
        read_only_fields = fields


class ReservationAmendmentHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ReservationAmendmentHistory
        fields = '__all__'
        read_only_fields = [field.name for field in ReservationAmendmentHistory._meta.fields]


class GuestCompanionSerializer(serializers.ModelSerializer):
    class Meta:
        model = GuestCompanion
        fields = '__all__'
        read_only_fields = ['created_at']


class WaitlistEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = WaitlistEntry
        fields = '__all__'
        read_only_fields = [
            'reference', 'status', 'offered_at', 'offer_expires_at',
            'converted_reservation', 'created_by', 'created_at',
        ]


class ReservationSerializer(serializers.ModelSerializer):
    guest_detail = UserProfileSerializer(source='guest', read_only=True)
    room_detail = RoomSerializer(source='room', read_only=True)
    nights = serializers.IntegerField(read_only=True)
    status_history = ReservationStatusHistorySerializer(many=True, read_only=True)
    room_assignments = ReservationRoomAssignmentSerializer(many=True, read_only=True)
    amendments = ReservationAmendmentHistorySerializer(many=True, read_only=True)
    companions = GuestCompanionSerializer(many=True, read_only=True)

    class Meta:
        model = Reservation
        fields = '__all__'
        read_only_fields = [
            'reservation_number', 'total_amount', 'nightly_rate', 'status', 'created_by',
            'source', 'channel_reference', 'price_snapshot', 'policy_snapshot',
        ]
        extra_kwargs = {'guest': {'required': False}}

    def validate(self, data):
        check_in = data.get('check_in_date')
        check_out = data.get('check_out_date')
        if check_in and check_out and check_out <= check_in:
            raise serializers.ValidationError('Check-out must be after check-in.')
        request = self.context.get('request')
        if (
            self.instance is None
            and request
            and request.user.is_authenticated
            and (request.user.is_superuser or request.user.role in {'admin', 'manager', 'receptionist'})
            and not data.get('guest')
        ):
            raise serializers.ValidationError({'guest': 'Staff must select a guest.'})
        return data


class BookingQuoteSerializer(serializers.ModelSerializer):
    room_detail = RoomSerializer(source='room', read_only=True)
    promotion_code = serializers.CharField(write_only=True, required=False, allow_blank=True)
    extras = serializers.PrimaryKeyRelatedField(
        queryset=BookableExtra.objects.filter(is_active=True), many=True,
        write_only=True, required=False,
    )

    class Meta:
        model = BookingQuote
        fields = '__all__'
        read_only_fields = [
            'reference', 'currency', 'subtotal', 'tax_total', 'total', 'price_snapshot',
            'policy_snapshot', 'status', 'expires_at', 'converted_reservation',
            'created_by', 'created_at', 'promotion', 'discount_total', 'extra_total',
        ]
        extra_kwargs = {'guest': {'required': False}, 'email': {'required': False}}

    def validate(self, data):
        request = self.context.get('request')
        if (
            request and request.user.is_authenticated
            and (request.user.is_superuser or request.user.role in {'admin', 'manager', 'receptionist'})
            and not data.get('guest')
        ):
            raise serializers.ValidationError({'guest': 'Staff must select a guest.'})
        return data


class CorporateAccountSerializer(serializers.ModelSerializer):
    class Meta:
        model = CorporateAccount
        fields = '__all__'
        read_only_fields = ['created_at']


class GroupBookingSerializer(serializers.ModelSerializer):
    reservation_count = serializers.IntegerField(source='reservations.count', read_only=True)

    class Meta:
        model = GroupBooking
        fields = '__all__'
        read_only_fields = ['reference', 'created_by', 'created_at']

    def validate(self, data):
        arrival = data.get('arrival_date', getattr(self.instance, 'arrival_date', None))
        departure = data.get('departure_date', getattr(self.instance, 'departure_date', None))
        if arrival and departure and departure <= arrival:
            raise serializers.ValidationError({'departure_date': 'Departure must be after arrival.'})
        return data


class ReservationDiscountRequestSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReservationDiscountRequest
        fields = '__all__'
        read_only_fields = ['status', 'requested_by', 'reviewed_by', 'review_note', 'requested_at', 'reviewed_at']
