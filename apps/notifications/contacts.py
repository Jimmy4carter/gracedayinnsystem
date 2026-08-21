import json
import urllib.error
import urllib.request
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from apps.frontend.models import NewsletterSubscription

from .models import BrevoContactSync, ContactPreference, Suppression
from .http import open_brevo_request
from .services import DeliveryError


def contact_marketing_consent(email):
    subscription = NewsletterSubscription.objects.filter(email__iexact=email).first()
    preference = ContactPreference.objects.filter(email__iexact=email, purpose='marketing').first()
    suppressed = Suppression.objects.filter(email__iexact=email).exists()
    return bool(
        subscription and subscription.is_active and preference and preference.consent_granted
        and not suppressed
    )


def enqueue_contact_sync(email):
    email = email.strip().lower()
    consent = contact_marketing_consent(email)
    record, _ = BrevoContactSync.objects.update_or_create(
        email=email,
        defaults={
            'desired_marketing_consent': consent, 'status': 'pending',
            'next_attempt_at': None, 'last_error': '',
        },
    )
    return record


def _send_contact(record):
    api_key = getattr(settings, 'BREVO_API_KEY', '')
    if not api_key:
        raise DeliveryError('BREVO_API_KEY is not configured.', transient=False)
    payload = {
        'email': record.email, 'updateEnabled': True,
        'emailBlacklisted': not record.desired_marketing_consent,
        'attributes': {'MARKETING_CONSENT': record.desired_marketing_consent},
    }
    list_id = getattr(settings, 'BREVO_CONTACT_LIST_ID', 0)
    if list_id and record.desired_marketing_consent:
        payload['listIds'] = [list_id]
    request = urllib.request.Request(
        'https://api.brevo.com/v3/contacts', data=json.dumps(payload).encode(), method='POST',
        headers={'api-key': api_key, 'accept': 'application/json', 'content-type': 'application/json'},
    )
    try:
        with open_brevo_request(request, timeout=15) as response:
            return json.loads(response.read().decode() or '{}')
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors='replace')[:400]
        raise DeliveryError(
            f'Brevo Contacts HTTP {exc.code}: {detail}',
            transient=exc.code in {425, 429} or exc.code >= 500, response_code=exc.code,
        ) from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise DeliveryError(f'Brevo Contacts connection failed: {exc}') from exc


@transaction.atomic
def process_contact_sync(record_id):
    record = BrevoContactSync.objects.select_for_update().get(pk=record_id)
    record.desired_marketing_consent = contact_marketing_consent(record.email)
    record.attempt_count += 1
    try:
        response = _send_contact(record)
    except DeliveryError as exc:
        retry = exc.transient and record.attempt_count < 5
        record.status = 'deferred' if retry else 'failed'
        record.next_attempt_at = timezone.now() + timedelta(minutes=2 ** record.attempt_count) if retry else None
        record.last_error = str(exc)[:500]
    else:
        record.status = 'synced' if record.desired_marketing_consent else 'suppressed'
        record.provider_contact_id = str(response.get('id', record.provider_contact_id or ''))
        record.last_synced_at = timezone.now()
        record.next_attempt_at = None
        record.last_error = ''
    record.save()
    return record


def sync_brevo_contacts(limit=100):
    for email in NewsletterSubscription.objects.values_list('email', flat=True).iterator():
        record = BrevoContactSync.objects.filter(email__iexact=email).first()
        desired = contact_marketing_consent(email)
        if not record or record.desired_marketing_consent != desired:
            enqueue_contact_sync(email)
    due = BrevoContactSync.objects.filter(status='pending') | BrevoContactSync.objects.filter(
        status='deferred', next_attempt_at__lte=timezone.now()
    )
    ids = list(due.order_by('updated_at').values_list('id', flat=True)[:limit])
    return [process_contact_sync(record_id) for record_id in ids]
