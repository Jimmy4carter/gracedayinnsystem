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
        read_only_fields = ['order_number', 'total']
