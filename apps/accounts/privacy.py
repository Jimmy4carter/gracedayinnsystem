import json
import uuid
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone

from .models import DataPrivacyRequest, DataPrivacyRequestHistory, GuestProfile, UserProfile


def _staff(actor):
    return actor.is_superuser or actor.role in {'admin', 'manager'}


@transaction.atomic
def submit_privacy_request(*, guest, request_type, details=''):
    if guest.role != 'guest' or guest.merged_into_id:
        raise ValidationError('Only active guest records can submit privacy requests.')
    if request_type not in dict(DataPrivacyRequest.TYPE_CHOICES):
        raise ValidationError('Unknown privacy request type.')
    if DataPrivacyRequest.objects.filter(
        guest=guest, request_type=request_type, status__in=['submitted', 'approved']
    ).exists():
        raise ValidationError('An active request of this type already exists.')
    item = DataPrivacyRequest.objects.create(
        guest=guest, request_type=request_type, details=details.strip(),
    )
    DataPrivacyRequestHistory.objects.create(
        request=item, action='submit', from_status='', to_status='submitted', actor=guest,
    )
    return item


@transaction.atomic
def review_privacy_request(*, request_id, action, actor, reason=''):
    if not _staff(actor):
        raise ValidationError('Only managers or administrators can review privacy requests.')
    item = DataPrivacyRequest.objects.select_for_update().get(pk=request_id)
    if item.status != 'submitted' or action not in {'approve', 'reject'}:
        raise ValidationError('This privacy request cannot receive that decision.')
    if action == 'reject' and not reason.strip():
        raise ValidationError('A rejection reason is required.')
    previous = item.status
    item.status = 'approved' if action == 'approve' else 'rejected'
    item.decision_reason = reason.strip()
    item.reviewed_by = actor
    item.reviewed_at = timezone.now()
    item.save(update_fields=['status', 'decision_reason', 'reviewed_by', 'reviewed_at'])
    DataPrivacyRequestHistory.objects.create(
        request=item, action=action, from_status=previous, to_status=item.status,
        actor=actor, notes=reason.strip(),
    )
    return item


def _export_payload(guest):
    reservations = guest.reservations.select_related('room').all()
    return {
        'generated_at': timezone.now().isoformat(),
        'profile': {
            'username': guest.username, 'first_name': guest.first_name,
            'last_name': guest.last_name, 'email': guest.email, 'phone': guest.phone,
            'address': guest.address, 'nationality': guest.nationality,
            'id_type': guest.id_type, 'id_last_four': guest.id_last_four,
        },
        'reservations': list(reservations.values(
            'reservation_number', 'check_in_date', 'check_out_date', 'status',
            'source', 'total_amount', 'room__number',
        )),
        'invoices': list(guest.invoices.values(
            'invoice_number', 'status', 'subtotal', 'tax_amount', 'total', 'amount_paid', 'balance',
        )),
        'folios': [{
            'reference': str(folio.reference), 'status': folio.status,
            'currency': folio.currency,
            'entries': list(folio.entries.values(
                'reference', 'direction', 'entry_type', 'description', 'amount', 'posted_at'
            )),
        } for folio in guest.folios.prefetch_related('entries')],
        'consents': list(guest.consent_history.values(
            'purpose', 'wording_version', 'granted', 'source', 'created_at'
        )),
        'inquiries': [{
            'reference': str(case.reference), 'subject': case.subject, 'status': case.status,
            'messages': list(case.messages.filter(is_internal=False).values('sender_name', 'body', 'created_at')),
        } for case in guest.inquiry_cases.prefetch_related('messages')],
        'chat_transcripts': [{
            'reference': str(chat.reference), 'status': chat.status,
            'messages': list(chat.messages.exclude(sender_type='internal').values(
                'sender_type', 'body', 'created_at'
            )),
        } for chat in guest.chat_conversations.prefetch_related('messages')],
    }


def _anonymization_blockers(guest):
    blockers = []
    if guest.privacy_legal_hold:
        blockers.append('legal hold')
    if guest.reservations.filter(status__in=['pending', 'confirmed', 'checked_in']).exists():
        blockers.append('active reservation')
    if any(folio.balance != 0 for folio in guest.folios.filter(status='open').prefetch_related('entries')):
        blockers.append('non-zero open folio')
    return blockers


@transaction.atomic
def execute_privacy_request(*, request_id, actor):
    if not _staff(actor):
        raise ValidationError('Only managers or administrators can execute privacy requests.')
    item = DataPrivacyRequest.objects.select_for_update().select_related('guest').get(pk=request_id)
    if item.status != 'approved':
        raise ValidationError('Only approved privacy requests can be executed.')
    guest = UserProfile.objects.select_for_update().get(pk=item.guest_id)
    if item.request_type == 'export':
        content = json.dumps(_export_payload(guest), default=str, indent=2).encode()
        item.artifact.save(
            f'guest-export-{item.reference}.json', ContentFile(content), save=False,
        )
        item.artifact_expires_at = timezone.now() + timedelta(days=7)
    elif item.request_type == 'anonymize':
        blockers = _anonymization_blockers(guest)
        if blockers:
            raise ValidationError(f'Anonymization blocked by: {", ".join(blockers)}.')
        old_email = guest.email
        anonymous_email = f'anonymized-{guest.id}@invalid.local'
        if guest.avatar:
            guest.avatar.delete(save=False)
        guest.booking_quotes.update(email='')
        guest.inquiry_cases.update(requester_name='Anonymized guest', requester_email=anonymous_email)
        guest.inquiry_messages.update(sender_name='Anonymized guest', sender_email=anonymous_email)
        guest.chat_conversations.update(visitor_name='Anonymized guest', visitor_email='')
        GuestProfile.objects.filter(user=guest).update(
            date_of_birth=None, preferences='', notes='',
        )
        if old_email:
            # Retain only the minimum do-not-contact marker needed to prevent
            # accidental re-subscription after the operational profile is erased.
            from apps.frontend.models import NewsletterSubscription
            from apps.notifications.models import BrevoContactSync, ContactPreference, Suppression
            NewsletterSubscription.objects.filter(email__iexact=old_email).update(is_active=False)
            ContactPreference.objects.filter(email__iexact=old_email).update(
                consent_granted=False, withdrawn_at=timezone.now(),
            )
            BrevoContactSync.objects.filter(email__iexact=old_email).update(
                desired_marketing_consent=False, status='suppressed',
            )
            Suppression.objects.update_or_create(
                email=old_email.lower(), defaults={'reason': 'manual', 'source': 'privacy_anonymization'},
            )
        guest.username = f'anonymized-{guest.id}-{uuid.uuid4().hex[:8]}'
        guest.first_name = guest.last_name = guest.email = guest.phone = guest.address = ''
        guest.id_type = guest.id_last_four = guest.nationality = ''
        guest.avatar = None
        guest.is_active = False
        guest.anonymized_at = timezone.now()
        guest.set_unusable_password()
        guest.save()
    item.status = 'completed'
    item.completed_at = timezone.now()
    item.save(update_fields=['status', 'artifact', 'artifact_expires_at', 'completed_at'])
    DataPrivacyRequestHistory.objects.create(
        request=item, action='execute', from_status='approved', to_status='completed', actor=actor,
        notes=f'Completed {item.request_type} under controlled workflow.',
    )
    return item
