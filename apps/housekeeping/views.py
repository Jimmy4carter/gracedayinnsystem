from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from django.utils import timezone
from .models import HousekeepingTask
from .serializers import HousekeepingTaskSerializer


class HousekeepingTaskViewSet(viewsets.ModelViewSet):
    queryset = HousekeepingTask.objects.select_related('room', 'assigned_to').all()
    serializer_class = HousekeepingTaskSerializer
    permission_classes = [permissions.IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['status', 'priority', 'task_type', 'assigned_to', 'room']

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        task = self.get_object()
        task.status = 'in_progress'
        task.started_at = timezone.now()
        task.save()
        return Response(HousekeepingTaskSerializer(task).data)

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        task = self.get_object()
        task.status = 'completed'
        task.completed_at = timezone.now()
        task.save()
        if task.room.status == 'housekeeping':
            task.room.status = 'available'
            task.room.save()
        return Response(HousekeepingTaskSerializer(task).data)
