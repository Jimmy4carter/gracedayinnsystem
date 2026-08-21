from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response
from .models import CommunicationTemplate, Notification, OutboundMessage
from .serializers import (
    CommunicationTemplateSerializer, NotificationSerializer, OutboundMessageSerializer,
)
from apps.accounts.permissions import RoleActionPermission
from apps.accounts.api_audit import ApiAuditMixin

ALL_ROLES = {'admin', 'manager', 'receptionist', 'housekeeping', 'guest'}


class NotificationViewSet(ApiAuditMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = NotificationSerializer
    permission_classes = [RoleActionPermission]
    action_roles = {
        'list': ALL_ROLES, 'retrieve': ALL_ROLES,
        'mark_read': ALL_ROLES, 'mark_all_read': ALL_ROLES, 'unread_count': ALL_ROLES,
    }

    def get_queryset(self):
        return Notification.objects.filter(recipient=self.request.user)

    @action(detail=True, methods=['post'])
    def mark_read(self, request, pk=None):
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response(NotificationSerializer(notification).data)

    @action(detail=False, methods=['post'])
    def mark_all_read(self, request):
        self.get_queryset().filter(is_read=False).update(is_read=True)
        return Response({'message': 'All notifications marked as read.'})

    @action(detail=False, methods=['get'])
    def unread_count(self, request):
        count = self.get_queryset().filter(is_read=False).count()
        return Response({'count': count})


class CommunicationTemplateViewSet(ApiAuditMixin, viewsets.ModelViewSet):
    queryset = CommunicationTemplate.objects.all()
    serializer_class = CommunicationTemplateSerializer
    permission_classes = [RoleActionPermission]
    action_roles = {
        'list': {'admin', 'manager'}, 'retrieve': {'admin', 'manager'},
        'create': {'admin'}, 'update': {'admin'}, 'partial_update': {'admin'},
        'destroy': {'admin'},
    }


class OutboundMessageViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = OutboundMessage.objects.select_related('recipient', 'template').prefetch_related('events')
    serializer_class = OutboundMessageSerializer
    permission_classes = [RoleActionPermission]
    action_roles = {'list': {'admin', 'manager'}, 'retrieve': {'admin', 'manager'}}
