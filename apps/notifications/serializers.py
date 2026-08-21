from rest_framework import serializers
from .models import CommunicationTemplate, DeliveryEvent, Notification, OutboundMessage


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = '__all__'
        read_only_fields = ['created_at']


class CommunicationTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = CommunicationTemplate
        fields = '__all__'
        read_only_fields = ['published_at', 'created_at']


class DeliveryEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeliveryEvent
        fields = '__all__'
        read_only_fields = [field.name for field in DeliveryEvent._meta.fields]


class OutboundMessageSerializer(serializers.ModelSerializer):
    events = DeliveryEventSerializer(many=True, read_only=True)

    class Meta:
        model = OutboundMessage
        fields = '__all__'
        read_only_fields = [field.name for field in OutboundMessage._meta.fields]
