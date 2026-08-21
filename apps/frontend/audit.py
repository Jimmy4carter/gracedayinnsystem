import logging

from django.core.exceptions import ValidationError

from .models import AuditChainHead, AuditLog


ZERO_HASH = '0' * 64
logger = logging.getLogger(__name__)


def record_audit_event(*, event_type, action, target_model, target_id='', actor=None,
                       details=None, ip_address=None, user_agent=''):
    return AuditLog.objects.create(
        actor=actor, event_type=event_type, action=action,
        target_model=target_model, target_id=str(target_id or ''),
        details=details or {}, ip_address=ip_address,
        user_agent=(user_agent or '')[:255],
    )


class AuthenticatedMutationAuditMiddleware:
    """Append a payload-free audit event for successful authenticated non-API writes."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, 'user', None)
        if (
            request.method in {'POST', 'PUT', 'PATCH', 'DELETE'}
            and response.status_code < 400
            and user and user.is_authenticated
            and not request.path.startswith('/api/')
            and not request.path.startswith('/static/')
        ):
            try:
                record_audit_event(
                    actor=user, event_type='security', action=f'http_{request.method.lower()}',
                    target_model='HttpRequest', target_id=getattr(request, 'request_id', ''),
                    details={'path': request.path, 'status_code': response.status_code},
                    ip_address=request.META.get('REMOTE_ADDR'),
                    user_agent=request.META.get('HTTP_USER_AGENT', ''),
                )
            except Exception:
                logger.exception('Unable to append authenticated mutation audit event')
        return response


def verify_audit_chain():
    previous_hash = ZERO_HASH
    expected_sequence = 1
    checked = 0
    for item in AuditLog.objects.order_by('sequence').iterator():
        if item.sequence != expected_sequence:
            raise ValidationError(
                f'Audit sequence discontinuity: expected {expected_sequence}, found {item.sequence}.'
            )
        if item.previous_hash != previous_hash:
            raise ValidationError(f'Audit previous-hash mismatch at sequence {item.sequence}.')
        calculated = item.calculate_hash()
        if item.event_hash != calculated:
            raise ValidationError(f'Audit event-hash mismatch at sequence {item.sequence}.')
        previous_hash = item.event_hash
        expected_sequence += 1
        checked += 1
    head, _ = AuditChainHead.objects.get_or_create(pk=1)
    if head.last_sequence != checked or head.last_hash != previous_hash:
        raise ValidationError('Audit chain head does not match the verified event history.')
    return {'events_checked': checked, 'last_sequence': checked, 'last_hash': previous_hash}
