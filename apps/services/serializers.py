from rest_framework import serializers
from .models import ServiceCategory, MenuItem, ServiceOrder, ServiceOrderItem


class ServiceCategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceCategory
        fields = '__all__'


class MenuItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = MenuItem
        fields = '__all__'


class ServiceOrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = ServiceOrderItem
        fields = '__all__'
        read_only_fields = ['unit_price', 'subtotal']


class ServiceOrderSerializer(serializers.ModelSerializer):
    items = ServiceOrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = ServiceOrder
        fields = '__all__'
        read_only_fields = ['order_number', 'total', 'status']
        extra_kwargs = {'guest': {'required': False}}

    def validate(self, data):
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
