from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.template.loader import render_to_string
from django.utils import timezone

from .models import (
    InquiryAttachment, InquiryCase, InquiryMessage, InquiryRoutingRule, InquiryStatusHistory,
)
from .services import enqueue_email


@transaction.atomic
def create_inquiry(*, requester_name, requester_email, subject, message, requester=None,
                   category='general', source='website', reservation=None):
    now = timezone.now()
    priority = 'high' if category in {'complaint', 'billing'} else 'normal'
    rule = InquiryRoutingRule.objects.filter(
        category=category, is_active=True,
    ).filter(models.Q(source='') | models.Q(source=source)).select_related('owner').first()
    if rule:
        priority = rule.priority
    case = InquiryCase.objects.create(
        requester_name=requester_name, requester_email=requester_email.lower(),
        requester=requester, subject=subject, category=category, source=source,
        reservation=reservation, priority=priority, owner=rule.owner if rule else None,
        first_response_due_at=now + timedelta(hours=rule.first_response_hours if rule else (2 if priority == 'high' else 4)),
        resolution_due_at=now + timedelta(hours=rule.resolution_hours if rule else (24 if priority == 'high' else 48)),
    )
    InquiryMessage.objects.create(
        case=case, sender=requester, sender_name=requester_name,
        sender_email=requester_email.lower(), body=message,
    )
    InquiryStatusHistory.objects.create(
        case=case, from_status='', to_status='new', action='create', actor=requester,
    )
    acknowledgement_html = render_to_string('emails/inquiry_acknowledgement.html', {'case': case})
    enqueue_email(
        purpose='inquiry_acknowledgement', recipient_email=requester_email,
        recipient=requester, recipient_name=requester_name,
        subject=f'We received your inquiry — {case.reference}',
        html_body=acknowledgement_html,
        text_body=f'We received your inquiry. Reference: {case.reference}.',
        related_model='InquiryCase', related_id=case.id,
        idempotency_key=f'inquiry-ack:{case.reference}',
    )
    return case


@transaction.atomic
def transition_inquiry(*, case_id, action, actor, notes='', owner=None, outcome=''):
    case = InquiryCase.objects.select_for_update().get(pk=case_id)
    rules = {
        'acknowledge': ({'new'}, 'acknowledged'),
        'start': ({'new', 'acknowledged', 'awaiting_guest'}, 'in_progress'),
        'await_guest': ({'in_progress'}, 'awaiting_guest'),
        'resolve': ({'in_progress', 'awaiting_guest'}, 'resolved'),
        'close': ({'resolved'}, 'closed'),
        'reopen': ({'resolved', 'closed'}, 'in_progress'),
        'spam': ({'new', 'acknowledged'}, 'spam'),
    }
    if action not in rules:
        raise ValidationError('Unknown inquiry action.')
    allowed, target = rules[action]
    if case.status not in allowed:
        raise ValidationError(f'Cannot move inquiry from {case.status} to {target}.')
    previous = case.status
    case.status = target
    if owner is not None:
        case.owner = owner
    elif action in {'acknowledge', 'start'} and not case.owner_id:
        case.owner = actor
    if not case.first_responded_at and action in {'acknowledge', 'start', 'await_guest', 'resolve'}:
        case.first_responded_at = timezone.now()
    if action == 'resolve':
        case.resolved_at, case.outcome = timezone.now(), outcome or notes
    elif action == 'reopen':
        case.resolved_at, case.outcome = None, ''
    case.save()
    InquiryStatusHistory.objects.create(
        case=case, from_status=previous, to_status=target, action=action,
        actor=actor, notes=notes,
    )
    return case


@transaction.atomic
def add_inquiry_reply(*, case_id, actor, body, internal=False):
    case = InquiryCase.objects.select_for_update().get(pk=case_id)
    if case.status in {'closed', 'spam'}:
        raise ValidationError('Closed or spam inquiries cannot receive replies.')
    reply = InquiryMessage.objects.create(
        case=case, sender=actor, sender_name=actor.get_full_name() or actor.username,
        sender_email=actor.email, body=body, is_internal=internal,
    )
    if not internal:
        reply_html = render_to_string('emails/inquiry_reply.html', {
            'case': case, 'reply': reply, 'agent_name': actor.get_full_name() or actor.username,
        })
        enqueue_email(
            purpose='inquiry_reply', recipient_email=case.requester_email,
            recipient=case.requester, recipient_name=case.requester_name,
            subject=f'Re: {case.subject} — {case.reference}',
            html_body=reply_html, text_body=body,
            related_model='InquiryCase', related_id=case.id,
            idempotency_key=f'inquiry-reply:{reply.id}',
        )
        if not case.first_responded_at:
            case.first_responded_at = timezone.now()
            case.save(update_fields=['first_responded_at', 'updated_at'])
    return reply


def add_inquiry_attachment(*, case, uploaded_file, actor):
    allowed = {'application/pdf', 'image/jpeg', 'image/png', 'text/plain'}
    content_type = (getattr(uploaded_file, 'content_type', '') or '').lower()
    if content_type not in allowed:
        raise ValidationError('Only PDF, JPEG, PNG and plain-text evidence files are allowed.')
    if uploaded_file.size > 5 * 1024 * 1024:
        raise ValidationError('Inquiry attachments cannot exceed 5 MB.')
    return InquiryAttachment.objects.create(
        case=case, file=uploaded_file, original_name=uploaded_file.name[:255],
        content_type=content_type, size=uploaded_file.size, uploaded_by=actor,
    )
