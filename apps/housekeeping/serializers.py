from rest_framework import serializers
from .models import (
    HousekeepingTask, HousekeepingTaskHistory, MaintenanceTicket,
    MaintenanceTicketHistory,
)


class HousekeepingTaskHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = HousekeepingTaskHistory
        fields = '__all__'
        read_only_fields = [field.name for field in HousekeepingTaskHistory._meta.fields]


class HousekeepingTaskSerializer(serializers.ModelSerializer):
    history = HousekeepingTaskHistorySerializer(many=True, read_only=True)

    class Meta:
        model = HousekeepingTask
        fields = '__all__'
        read_only_fields = [
            'status', 'started_at', 'completed_at', 'verified_at', 'verified_by',
            'completion_notes', 'inspection_notes', 'created_by', 'created_at', 'updated_at',
        ]


class MaintenanceTicketHistorySerializer(serializers.ModelSerializer):
    class Meta:
        model = MaintenanceTicketHistory
        fields = '__all__'
        read_only_fields = [field.name for field in MaintenanceTicketHistory._meta.fields]


class MaintenanceTicketSerializer(serializers.ModelSerializer):
    history = MaintenanceTicketHistorySerializer(many=True, read_only=True)

    class Meta:
        model = MaintenanceTicket
        fields = '__all__'
        read_only_fields = [
            'reference', 'status', 'reported_by', 'actual_cost', 'resolution_notes',
            'started_at', 'resolved_at', 'approved_at', 'approved_by',
            'created_at', 'updated_at',
        ]
