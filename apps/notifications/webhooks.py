import hashlib
import hmac
import json
from datetime import datetime, timezone as dt_timezone

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from .models import ContactPreference, DeliveryEvent, OutboundMessage, Suppression

EVENT_MAP = {
    'sent': 'sent', 'delivered': 'delivered', 'opened': 'opened', 'clicks': 'clicked',
    'clicked': 'clicked', 'deferred': 'deferred', 'soft_bounce': 'soft_bounce',
    'hard_bounce': 'hard_bounce', 'blocked': 'blocked', 'invalid_email': 'invalid',
    'complaint': 'complaint', 'unsubscribed': 'unsubscribed', 'error': 'error',
}


@csrf_exempt
@require_POST
def brevo_webhook(request):
    expected = getattr(settings, 'BREVO_WEBHOOK_TOKEN', '')
    supplied = request.headers.get('X-Brevo-Webhook-Token', '')
    if not expected or not hmac.compare_digest(expected, supplied):
        return JsonResponse({'detail': 'Invalid webhook authentication.'}, status=401)
    try:
        payload = json.loads(request.body)
    except (TypeError, ValueError):
        return JsonResponse({'detail': 'Invalid JSON.'}, status=400)
    events = payload if isinstance(payload, list) else [payload]
    processed = 0
    for item in events:
        event_type = EVENT_MAP.get(str(item.get('event', '')).lower().replace(' ', '_'))
        if not event_type:
            continue
        provider_message_id = item.get('message-id') or item.get('messageId') or ''
        email = (item.get('email') or '').lower()
        fingerprint = item.get('id') or item.get('event_id') or hashlib.sha256(
            json.dumps(item, sort_keys=True).encode()
        ).hexdigest()
        ts = item.get('ts_event') or item.get('ts')
        occurred_at = datetime.fromtimestamp(float(ts), tz=dt_timezone.utc) if ts else None
        message = OutboundMessage.objects.filter(provider_message_id=provider_message_id).first()
        _, created = DeliveryEvent.objects.get_or_create(
            provider_event_id=f'brevo:{fingerprint}:{event_type}',
            defaults={
                'message': message, 'event_type': event_type,
                'provider_message_id': provider_message_id, 'recipient_email': email,
                'occurred_at': occurred_at,
                'metadata': {key: value for key, value in item.items() if key != 'email'},
            },
        )
        if not created:
            continue
        processed += 1
        if message:
            new_status = {'delivered': 'delivered', 'deferred': 'deferred', 'soft_bounce': 'deferred',
                          'hard_bounce': 'bounced', 'invalid': 'bounced', 'blocked': 'bounced',
                          'complaint': 'complained', 'error': 'failed'}.get(event_type)
            if new_status:
                message.status = new_status
                if event_type == 'delivered':
                    message.delivered_at = occurred_at or timezone.now()
                message.save(update_fields=['status', 'delivered_at', 'updated_at'])
        reason = {'hard_bounce': 'hard_bounce', 'invalid': 'invalid', 'complaint': 'complaint',
                  'unsubscribed': 'unsubscribe'}.get(event_type)
        if email and reason:
            Suppression.objects.update_or_create(email=email, defaults={'reason': reason, 'source': 'brevo'})
            if event_type == 'unsubscribed':
                ContactPreference.objects.update_or_create(
                    email=email, purpose='marketing', defaults={
                        'consent_granted': False, 'consent_source': 'brevo_webhook',
                        'withdrawn_at': occurred_at or timezone.now(),
                    },
                )
    return JsonResponse({'processed': processed})
