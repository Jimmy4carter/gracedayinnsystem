import uuid

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from django.utils.html import strip_tags

from .models import ChatConversation, ChatMessage, ChatOperatingHour, ChatStatusHistory

CHAT_STAFF = {'admin', 'manager', 'receptionist'}


def chat_is_open(at=None):
    local = timezone.localtime(at or timezone.now())
    hours = ChatOperatingHour.objects.filter(weekday=local.weekday()).first()
    if not hours:
        return True
    return not hours.is_closed and hours.opens_at <= local.time().replace(tzinfo=None) < hours.closes_at


def can_access_conversation(user, conversation, visitor_token=None):
    if user and user.is_authenticated:
        return user.is_superuser or user.role in CHAT_STAFF or conversation.guest_id == user.id
    return visitor_token and str(conversation.visitor_token) == str(visitor_token)


@transaction.atomic
def start_conversation(*, name='', email='', guest=None, body='', queue='front_desk'):
    offline = not chat_is_open()
    if offline and not (email or (guest and guest.email)):
        raise ValidationError('An email address is required when live chat is offline.')
    conversation = ChatConversation.objects.create(
        visitor_name=name, visitor_email=email.lower(), guest=guest, queue=queue,
        last_message_at=timezone.now(), status='waiting' if offline else 'queued',
        is_offline_capture=offline,
    )
    ChatStatusHistory.objects.create(
        conversation=conversation, from_status='', to_status=conversation.status,
        action='offline_capture' if offline else 'start', actor=guest,
    )
    if body:
        send_chat_message(
            conversation=conversation, actor=guest, visitor_token=conversation.visitor_token,
            body=body, client_message_id=uuid.uuid4(),
        )
    if offline:
        from .inquiries import create_inquiry
        conversation.inquiry = create_inquiry(
            requester_name=name or (guest.get_full_name() if guest else 'Chat visitor'),
            requester_email=email or guest.email, requester=guest,
            subject='Offline live-chat request', message=body or 'Please contact me.',
            category='general', source='chat_offline',
        )
        conversation.save(update_fields=['inquiry', 'updated_at'])
    return conversation


@transaction.atomic
def submit_chat_satisfaction(*, conversation, rating, comment='', actor=None, visitor_token=None):
    locked = ChatConversation.objects.select_for_update().get(pk=conversation.pk)
    if not can_access_conversation(actor, locked, visitor_token):
        raise ValidationError('Conversation access denied.')
    if locked.status != 'closed':
        raise ValidationError('Feedback is available after the conversation closes.')
    if locked.satisfaction_submitted_at:
        raise ValidationError('Feedback has already been submitted.')
    try:
        rating = int(rating)
    except (TypeError, ValueError) as exc:
        raise ValidationError('Rating must be between 1 and 5.') from exc
    if rating not in range(1, 6):
        raise ValidationError('Rating must be between 1 and 5.')
    locked.satisfaction_rating = rating
    locked.satisfaction_comment = strip_tags(comment or '').strip()[:500]
    locked.satisfaction_submitted_at = timezone.now()
    locked.save(update_fields=['satisfaction_rating', 'satisfaction_comment', 'satisfaction_submitted_at', 'updated_at'])
    return locked


@transaction.atomic
def send_chat_message(*, conversation, body, actor=None, visitor_token=None,
                      client_message_id=None, internal=False):
    locked = ChatConversation.objects.select_for_update().get(pk=conversation.pk)
    if locked.status in {'closed', 'spam'}:
        raise ValidationError('This conversation is closed.')
    if not can_access_conversation(actor, locked, visitor_token):
        raise ValidationError('Conversation access denied.')
    cleaned = strip_tags(body or '').strip()
    max_length = 2000
    if not cleaned or len(cleaned) > max_length:
        raise ValidationError(f'Message must contain 1 to {max_length} characters.')
    rate_identity = actor.pk if actor and actor.is_authenticated else str(visitor_token)
    rate_key = f'chat-rate:{rate_identity}'
    count = cache.get(rate_key, 0)
    if count >= 30:
        raise ValidationError('Too many messages. Please wait a minute.')
    cache.set(rate_key, count + 1, 60)
    is_staff = actor and actor.is_authenticated and (actor.is_superuser or actor.role in CHAT_STAFF)
    if internal and not is_staff:
        raise ValidationError('Only agents can add internal notes.')
    sender_type = 'internal' if internal else ('agent' if is_staff else ('guest' if actor and actor.is_authenticated else 'visitor'))
    if client_message_id:
        existing = ChatMessage.objects.filter(
            conversation=locked, client_message_id=client_message_id
        ).first()
        if existing:
            return existing, False
    message = ChatMessage.objects.create(
        conversation=locked, sender=actor if actor and actor.is_authenticated else None,
        sender_type=sender_type, body=cleaned, client_message_id=client_message_id,
    )
    locked.last_message_at = timezone.now()
    if is_staff and not internal and not locked.first_agent_response_at:
        locked.first_agent_response_at = timezone.now()
    locked.save(update_fields=['last_message_at', 'first_agent_response_at', 'updated_at'])
    return message, True


@transaction.atomic
def transition_chat(*, conversation_id, action, actor, disposition=''):
    conversation = ChatConversation.objects.select_for_update().get(pk=conversation_id)
    if not actor.is_superuser and actor.role not in CHAT_STAFF:
        raise ValidationError('Only chat agents can manage conversations.')
    rules = {
        'assign': ({'queued', 'open', 'waiting'}, 'open'),
        'wait': ({'open'}, 'waiting'), 'reopen': ({'waiting', 'closed'}, 'open'),
        'close': ({'open', 'waiting'}, 'closed'), 'spam': ({'queued', 'open'}, 'spam'),
    }
    if action not in rules:
        raise ValidationError('Unknown chat action.')
    allowed, target = rules[action]
    if conversation.status not in allowed:
        raise ValidationError(f'Cannot move chat from {conversation.status} to {target}.')
    previous = conversation.status
    conversation.status = target
    if action == 'assign':
        conversation.assigned_to = actor
    if action == 'close':
        conversation.closed_at, conversation.disposition = timezone.now(), disposition
    if action == 'reopen':
        conversation.closed_at, conversation.disposition = None, ''
    conversation.save()
    ChatStatusHistory.objects.create(
        conversation=conversation, from_status=previous, to_status=target,
        action=action, actor=actor, metadata={'disposition': disposition},
    )
    return conversation
