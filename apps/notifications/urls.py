from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import CommunicationTemplateViewSet, NotificationViewSet, OutboundMessageViewSet
from .webhooks import brevo_webhook

router = DefaultRouter()
router.register('notifications', NotificationViewSet, basename='notification')
router.register('communication-templates', CommunicationTemplateViewSet, basename='communication-template')
router.register('outbound-messages', OutboundMessageViewSet, basename='outbound-message')

urlpatterns = [
    path('webhooks/brevo/', brevo_webhook, name='brevo-webhook'),
    path('', include(router.urls)),
]
