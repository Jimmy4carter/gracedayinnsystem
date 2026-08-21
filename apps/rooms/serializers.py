from rest_framework import serializers
from .models import Amenity, BookableExtra, DailyRate, InventoryBlock, Promotion, RatePlan, Room, RoomType, RoomTypeImage, TaxFee


class AmenitySerializer(serializers.ModelSerializer):
    class Meta:
        model = Amenity
        fields = '__all__'


class RoomTypeImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = RoomTypeImage
        fields = ['id', 'image', 'alt_text', 'caption', 'display_order', 'is_featured', 'is_published']


class RoomTypeSerializer(serializers.ModelSerializer):
    amenities = AmenitySerializer(many=True, read_only=True)
    amenity_ids = serializers.PrimaryKeyRelatedField(
        many=True, queryset=Amenity.objects.all(), source='amenities', write_only=True)
    gallery = serializers.SerializerMethodField()

    def get_gallery(self, instance):
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        may_manage = bool(user and user.is_authenticated and (
            user.is_superuser or user.role in {'admin', 'manager'}
        ))
        images = instance.gallery_images.all()
        if not may_manage:
            images = images.filter(is_published=True)
        return RoomTypeImageSerializer(images, many=True, context=self.context).data

    class Meta:
        model = RoomType
        fields = '__all__'


class RoomSerializer(serializers.ModelSerializer):
    room_type_detail = RoomTypeSerializer(source='room_type', read_only=True)
    current_price = serializers.DecimalField(max_digits=10, decimal_places=2, read_only=True)

    class Meta:
        model = Room
        fields = '__all__'

    def to_representation(self, instance):
        data = super().to_representation(instance)
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        if user and user.is_authenticated and not (
            user.is_superuser or user.role in {'admin', 'manager', 'receptionist', 'housekeeping'}
        ):
            data.pop('notes', None)
        return data


class DailyRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyRate
        fields = '__all__'


class RatePlanSerializer(serializers.ModelSerializer):
    daily_rates = DailyRateSerializer(many=True, read_only=True)

    class Meta:
        model = RatePlan
        fields = '__all__'


class TaxFeeSerializer(serializers.ModelSerializer):
    class Meta:
        model = TaxFee
        fields = '__all__'


class PromotionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Promotion
        fields = '__all__'
        read_only_fields = ['times_used', 'created_at']

    def validate(self, data):
        start = data.get('valid_from', getattr(self.instance, 'valid_from', None))
        end = data.get('valid_to', getattr(self.instance, 'valid_to', None))
        if start and end and end <= start:
            raise serializers.ValidationError({'valid_to': 'Promotion end must be after its start.'})
        if data.get('discount_type') == 'percentage' and data.get('amount', 0) > 100:
            raise serializers.ValidationError({'amount': 'Percentage discounts cannot exceed 100%.'})
        return data


class InventoryBlockSerializer(serializers.ModelSerializer):
    class Meta:
        model = InventoryBlock
        fields = '__all__'
        read_only_fields = ['status', 'created_by', 'released_by', 'released_at', 'created_at']

    def validate(self, data):
        if data['end_date'] <= data['start_date']:
            raise serializers.ValidationError({'end_date': 'Inventory block end must be after its start.'})
        return data


class BookableExtraSerializer(serializers.ModelSerializer):
    class Meta:
        model = BookableExtra
        fields = '__all__'
        read_only_fields = ['created_at']
