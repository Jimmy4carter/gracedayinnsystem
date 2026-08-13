from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import ManagementQuery, ManagementQueryHistory, ManagementQueryNote


@transaction.atomic
def create_management_query(*, title, description, actor, priority='normal',
                            source_model='', source_id='', assigned_to=None):
    hours = 4 if priority == 'urgent' else (12 if priority == 'high' else 24)
    query = ManagementQuery.objects.create(
        title=title, description=description, raised_by=actor, priority=priority,
        source_model=source_model, source_id=source_id, assigned_to=assigned_to,
        status='assigned' if assigned_to else 'open', due_at=timezone.now() + timedelta(hours=hours),
    )
    ManagementQueryHistory.objects.create(
        query=query, from_status='', to_status=query.status, action='raise', actor=actor,
    )
    return query


@transaction.atomic
def transition_management_query(*, query_id, action, actor, resolution='', assigned_to=None):
    query = ManagementQuery.objects.select_for_update().get(pk=query_id)
    rules = {
        'assign': ({'open', 'assigned'}, 'assigned'),
        'investigate': ({'open', 'assigned'}, 'investigating'),
        'resolve': ({'assigned', 'investigating'}, 'resolved'),
        'close': ({'resolved'}, 'closed'), 'reopen': ({'resolved', 'closed'}, 'investigating'),
    }
    if action not in rules:
        raise ValidationError('Unknown management query action.')
    allowed, target = rules[action]
    if query.status not in allowed:
        raise ValidationError(f'Cannot move query from {query.status} to {target}.')
    previous, query.status = query.status, target
    if action == 'assign':
        query.assigned_to = assigned_to or actor
    if action == 'resolve':
        if not resolution.strip():
            raise ValidationError('A resolution is required.')
        query.resolution, query.resolved_at = resolution.strip(), timezone.now()
    elif action == 'reopen':
        query.resolution, query.resolved_at = '', None
    query.save()
    ManagementQueryHistory.objects.create(
        query=query, from_status=previous, to_status=target, action=action, actor=actor,
    )
    return query


def add_management_query_note(*, query, actor, body, evidence=None):
    if not body.strip():
        raise ValidationError('A note is required.')
    return ManagementQueryNote.objects.create(
        query=query, author=actor, body=body.strip(), evidence=evidence,
    )
