from rest_framework import serializers
from .models import Room, RoomType, Amenity


class AmenitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Amenity
        fields = '__all__'


class RoomTypeSerializer(serializers.ModelSerializer):
    amenities = AmenitySerializer(many=True, read_only=True)
    amenity_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Amenity.objects.all(), source='amenities', write_only=True)

    class Meta:
        model = RoomType
        fields = '__all__'


class RoomSerializer(serializers.ModelSerializer):
    room_type_detail = RoomTypeSerializer(source='room_type', read_only=True)
    current_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Room
        fields = '__all__'
