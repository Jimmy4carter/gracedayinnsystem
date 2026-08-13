from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .audit import record_audit_event
from .models import PolicyDocument


def _require_admin(actor):
    if not (actor.is_superuser or actor.role == 'admin'):
        raise ValidationError('Only an administrator can approve or publish policy content.')


@transaction.atomic
def approve_policy(*, policy_id, actor, notes=''):
    _require_admin(actor)
    policy = PolicyDocument.objects.select_for_update().get(pk=policy_id)
    if not policy.effective_date:
        raise ValidationError('Set the effective date before approval.')
    if not policy.body.strip() or not policy.summary.strip():
        raise ValidationError('Policy summary and body are required before approval.')
    policy.review_status = 'approved'
    policy.review_notes = notes.strip()
    policy.reviewed_by = actor
    policy.reviewed_at = timezone.now()
    policy.approved_hash = policy.content_fingerprint()
    policy.is_published = False
    policy.save()
    record_audit_event(
        event_type='content', action='policy_approved', actor=actor,
        target_model='PolicyDocument', target_id=policy.id,
        details={'slug': policy.slug, 'version': policy.version},
    )
    return policy


@transaction.atomic
def publish_policy(*, policy_id, actor):
    _require_admin(actor)
    policy = PolicyDocument.objects.select_for_update().get(pk=policy_id)
    if policy.review_status != 'approved' or policy.approved_hash != policy.content_fingerprint():
        raise ValidationError('Approve the current policy version before publication.')
    policy.is_published = True
    policy.published_at = timezone.now()
    policy.full_clean()
    policy.save()
    record_audit_event(
        event_type='content', action='policy_published', actor=actor,
        target_model='PolicyDocument', target_id=policy.id,
        details={'slug': policy.slug, 'version': policy.version},
    )
    return policy


@transaction.atomic
def withdraw_policy(*, policy_id, actor, reason):
    _require_admin(actor)
    if not reason.strip():
        raise ValidationError('A withdrawal reason is required.')
    policy = PolicyDocument.objects.select_for_update().get(pk=policy_id)
    policy.is_published = False
    policy.save(update_fields=['is_published', 'published_at', 'updated_at'])
    record_audit_event(
        event_type='content', action='policy_withdrawn', actor=actor,
        target_model='PolicyDocument', target_id=policy.id,
        details={'slug': policy.slug, 'version': policy.version, 'reason': reason.strip()},
    )
    return policy
