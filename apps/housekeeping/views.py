from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from rest_framework.exceptions import ValidationError as ApiValidationError
from .models import HousekeepingTask, MaintenanceTicket
from .serializers import HousekeepingTaskSerializer, MaintenanceTicketSerializer
from .services import (
    create_housekeeping_task, create_maintenance_ticket, transition_housekeeping_task,
    transition_maintenance_ticket,
)
from apps.accounts.permissions import RoleActionPermission, has_role
from apps.accounts.api_audit import ApiAuditMixin

HOUSEKEEPING_ROLES = {'admin', 'manager', 'receptionist', 'housekeeping'}


class HousekeepingTaskViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = HousekeepingTask.objects.select_related('room', 'assigned_to').all()
    serializer_class = HousekeepingTaskSerializer
    permission_classes = [RoleActionPermission]
    action_roles = {action: HOUSEKEEPING_ROLES for action in ('list', 'retrieve', 'start', 'complete')}
    action_roles['create'] = {'admin', 'manager', 'receptionist'}
    action_roles.update({
        'verify': {'admin', 'manager', 'receptionist'}, 'reopen': {'admin', 'manager', 'receptionist'},
        'update': set(), 'partial_update': set(), 'destroy': set(),
    })
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['status', 'priority', 'task_type', 'assigned_to', 'room']

    def get_queryset(self):
        queryset = super().get_queryset()
        if has_role(self.request.user, {'admin', 'manager', 'receptionist'}):
            return queryset
        return queryset.filter(assigned_to=self.request.user)

    def perform_create(self, serializer):
        serializer.instance = create_housekeeping_task(
            actor=self.request.user, **serializer.validated_data
        )

    def _transition(self, request, action):
        try:
            task = transition_housekeeping_task(
                task_id=self.get_object().pk, action=action, actor=request.user,
                notes=request.data.get('notes', ''),
            )
        except DjangoValidationError as exc:
            raise ApiValidationError(exc.messages)
        return Response(self.get_serializer(task).data)

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None):
        return self._transition(request, 'start')

    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        return self._transition(request, 'complete')

    @action(detail=True, methods=['post'])
    def verify(self, request, pk=None):
        return self._transition(request, 'verify')

    @action(detail=True, methods=['post'])
    def reopen(self, request, pk=None):
        return self._transition(request, 'reopen')


class MaintenanceTicketViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = MaintenanceTicket.objects.select_related(
        'room', 'assigned_to', 'reported_by', 'approved_by'
    ).prefetch_related('history')
    serializer_class = MaintenanceTicketSerializer
    permission_classes = [RoleActionPermission]
    action_roles = {
        'list': HOUSEKEEPING_ROLES, 'retrieve': HOUSEKEEPING_ROLES,
        'create': HOUSEKEEPING_ROLES, 'start': HOUSEKEEPING_ROLES,
        'resolve': HOUSEKEEPING_ROLES, 'approve': {'admin', 'manager'},
        'cancel': {'admin', 'manager'}, 'reopen': {'admin', 'manager'},
        'update': set(), 'partial_update': set(), 'destroy': set(),
    }
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['status', 'priority', 'room', 'assigned_to', 'downtime_required']
    search_fields = ['title', 'description', 'reference']

    def get_queryset(self):
        queryset = super().get_queryset()
        if has_role(self.request.user, {'admin', 'manager', 'receptionist'}):
            return queryset
        return queryset.filter(models.Q(assigned_to=self.request.user) | models.Q(reported_by=self.request.user))

    def perform_create(self, serializer):
        serializer.instance = create_maintenance_ticket(
            actor=self.request.user, **serializer.validated_data
        )

    def _transition(self, request, action):
        try:
            ticket = transition_maintenance_ticket(
                ticket_id=self.get_object().pk, action=action, actor=request.user,
                notes=request.data.get('notes', ''), actual_cost=request.data.get('actual_cost'),
            )
        except DjangoValidationError as exc:
            raise ApiValidationError(exc.messages)
        return Response(self.get_serializer(ticket).data)

    @action(detail=True, methods=['post'])
    def start(self, request, pk=None): return self._transition(request, 'start')

    @action(detail=True, methods=['post'])
    def resolve(self, request, pk=None): return self._transition(request, 'resolve')

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None): return self._transition(request, 'approve')

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None): return self._transition(request, 'cancel')

    @action(detail=True, methods=['post'])
    def reopen(self, request, pk=None): return self._transition(request, 'reopen')
