from rest_framework import serializers
from .models import Reservation
from apps.rooms.serializers import RoomSerializer
from apps.accounts.serializers import UserProfileSerializer


class ReservationSerializer(serializers.ModelSerializer):
    guest_detail = UserProfileSerializer(source='guest', read_only=True)
    room_detail = RoomSerializer(source='room', read_only=True)
    nights = serializers.IntegerField(read_only=True)

    class Meta:
        model = Reservation
        fields = '__all__'
        read_only_fields = ['reservation_number', 'total_amount', 'nightly_rate']

    def validate(self, data):
        check_in = data.get('check_in_date')
        check_out = data.get('check_out_date')
        if check_in and check_out and check_out <= check_in:
            raise serializers.ValidationError('Check-out must be after check-in.')
        return data
