import json
import logging
import urllib.error
import urllib.request
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.utils import timezone

from .models import DeliveryAttempt, OutboundMessage, Suppression
from .http import open_brevo_request

logger = logging.getLogger(__name__)


class DeliveryError(Exception):
    def __init__(self, message, *, transient=True, response_code=None):
        super().__init__(message)
        self.transient = transient
        self.response_code = response_code


def enqueue_email(*, purpose, recipient_email, subject, html_body, text_body='', recipient=None,
                  recipient_name='', template=None, context=None, related_model='', related_id='',
                  idempotency_key=None, marketing=False, send_now=None):
    key = idempotency_key or str(uuid.uuid4())
    existing = OutboundMessage.objects.filter(idempotency_key=key).first()
    if existing:
        return existing, False
    suppression = Suppression.objects.filter(email__iexact=recipient_email).first()
    blocked = suppression and (marketing or suppression.reason in {'complaint', 'hard_bounce', 'invalid'})
    message = OutboundMessage.objects.create(
        purpose=purpose, recipient=recipient, recipient_email=recipient_email.lower(),
        recipient_name=recipient_name, template=template, subject=subject,
        html_body=html_body, text_body=text_body, context=context or {},
        provider=getattr(settings, 'EMAIL_DELIVERY_PROVIDER', 'django'),
        idempotency_key=key, related_model=related_model, related_id=str(related_id or ''),
        status='suppressed' if blocked else 'queued',
        last_error=f'Suppressed: {suppression.reason}' if blocked else '',
    )
    should_send = getattr(settings, 'EMAIL_OUTBOX_SEND_IMMEDIATELY', True) if send_now is None else send_now
    if should_send and not blocked:
        process_outbound_message(message.id)
        message.refresh_from_db()
    return message, True


def _send_django(message):
    email = EmailMultiAlternatives(
        subject=message.subject, body=message.text_body, from_email=None,
        to=[message.recipient_email],
    )
    email.attach_alternative(message.html_body, 'text/html')
    if email.send() != 1:
        raise DeliveryError('Django email backend did not accept the message.')
    return f'{message.provider}:{message.reference}'


def _send_brevo(message):
    api_key = getattr(settings, 'BREVO_API_KEY', '')
    if not api_key:
        raise DeliveryError('BREVO_API_KEY is not configured.', transient=False)
    headers = {'X-Mailin-custom': f'internal-message:{message.reference}'}
    if getattr(settings, 'BREVO_SANDBOX', False):
        headers['X-Sib-Sandbox'] = 'drop'
    recipient = {'email': message.recipient_email}
    if message.recipient_name.strip():
        recipient['name'] = message.recipient_name.strip()
    payload = {
        'sender': {'email': settings.DEFAULT_FROM_EMAIL,
                   'name': getattr(settings, 'BREVO_SENDER_NAME', 'GRACEDAY INN')},
        'to': [recipient],
        'subject': message.subject, 'htmlContent': message.html_body,
        'textContent': message.text_body, 'tags': [message.purpose, str(message.reference)],
        'headers': headers,
    }
    request = urllib.request.Request(
        'https://api.brevo.com/v3/smtp/email', data=json.dumps(payload).encode(), method='POST',
        headers={'api-key': api_key, 'accept': 'application/json', 'content-type': 'application/json',
                 'IdempotencyKey': message.idempotency_key},
    )
    try:
        with open_brevo_request(request, timeout=15) as response:
            return json.loads(response.read().decode() or '{}').get('messageId', '')
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors='replace')[:400]
        raise DeliveryError(
            f'Brevo HTTP {exc.code}: {detail}', transient=exc.code == 429 or exc.code >= 500,
            response_code=exc.code,
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise DeliveryError(f'Brevo connection failed: {exc}') from exc


@transaction.atomic
def process_outbound_message(message_id):
    message = OutboundMessage.objects.select_for_update().get(pk=message_id)
    if message.status not in {'queued', 'deferred'} or (
        message.next_attempt_at and message.next_attempt_at > timezone.now()
    ):
        return message
    message.status = 'processing'
    message.attempt_count += 1
    message.save(update_fields=['status', 'attempt_count', 'updated_at'])
    try:
        provider_id = _send_brevo(message) if message.provider == 'brevo' else _send_django(message)
    except DeliveryError as exc:
        retry = exc.transient and message.attempt_count < getattr(settings, 'EMAIL_OUTBOX_MAX_ATTEMPTS', 5)
        message.status = 'deferred' if retry else 'failed'
        message.next_attempt_at = timezone.now() + timedelta(minutes=2 ** min(message.attempt_count, 6)) if retry else None
        message.last_error = str(exc)[:500]
        message.save(update_fields=['status', 'next_attempt_at', 'last_error', 'updated_at'])
        DeliveryAttempt.objects.create(
            message=message, attempt_number=message.attempt_count, outcome=message.status,
            response_code=exc.response_code, error_detail=message.last_error,
        )
        logger.warning('Email delivery %s for message %s', message.status, message.reference)
        return message
    message.status, message.provider_message_id = 'accepted', provider_id
    message.accepted_at, message.next_attempt_at, message.last_error = timezone.now(), None, ''
    message.save(update_fields=['status', 'provider_message_id', 'accepted_at', 'next_attempt_at', 'last_error', 'updated_at'])
    DeliveryAttempt.objects.create(
        message=message, attempt_number=message.attempt_count, outcome='accepted',
        provider_message_id=provider_id,
    )
    return message


def process_due_outbox(limit=100):
    eligible = OutboundMessage.objects.filter(status='queued') | OutboundMessage.objects.filter(
        status='deferred', next_attempt_at__lte=timezone.now()
    )
    ids = list(eligible.order_by('created_at').values_list('id', flat=True)[:limit])
    return [process_outbound_message(message_id) for message_id in ids]
