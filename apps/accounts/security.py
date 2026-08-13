import hashlib

from django.conf import settings
from django.core.cache import cache


def _setting(name, default):
    return int(getattr(settings, name, default))


def _identity_key(kind, value):
    digest = hashlib.sha256((value or 'unknown').strip().lower().encode('utf-8')).hexdigest()
    return f'authentication:{kind}:{digest}'


def _keys(request, username):
    return (
        _identity_key('account', username),
        _identity_key('ip', request.META.get('REMOTE_ADDR') or 'unknown'),
    )


def login_is_blocked(request, username):
    limit = _setting('LOGIN_FAILURE_LIMIT', 5)
    return any(int(cache.get(key, 0)) >= limit for key in _keys(request, username))


def record_login_failure(request, username):
    window = _setting('LOGIN_FAILURE_WINDOW_SECONDS', 900)
    for key in _keys(request, username):
        if not cache.add(key, 1, timeout=window):
            try:
                cache.incr(key)
            except ValueError:
                cache.set(key, 1, timeout=window)


def clear_account_login_failures(username):
    cache.delete(_identity_key('account', username))


def record_authentication_event(request, action, user=None, username=''):
    from apps.frontend.models import AuditLog

    AuditLog.objects.create(
        actor=user if user and user.is_authenticated else None,
        event_type='security',
        action=action,
        target_model='UserProfile',
        target_id=str(user.pk) if user else '',
        details={'username': (username or getattr(user, 'username', ''))[:150]},
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:255],
    )
