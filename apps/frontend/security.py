import hashlib
import secrets
import time

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache


BOOKING_SESSION_KEYS = (
    'booking_request_data',
    'booking_verify_hash',
    'booking_verify_expires_at',
    'booking_verify_attempts',
)


def _setting(name, default):
    return int(getattr(settings, name, default))


def _rate_key(kind, value):
    digest = hashlib.sha256(value.strip().lower().encode('utf-8')).hexdigest()
    return f'booking-verification:{kind}:{digest}'


def _consume_rate_limit(key, limit, window_seconds):
    if cache.add(key, 1, timeout=window_seconds):
        return True
    try:
        return cache.incr(key) <= limit
    except ValueError:
        cache.set(key, 1, timeout=window_seconds)
        return True


def begin_booking_verification(request, booking_data):
    """Store only a password hash of the OTP and enforce email/IP send limits."""
    limit = _setting('BOOKING_OTP_SEND_LIMIT', 5)
    window = _setting('BOOKING_OTP_SEND_WINDOW_SECONDS', 3600)
    email_allowed = _consume_rate_limit(_rate_key('email', booking_data['email']), limit, window)
    ip = request.META.get('REMOTE_ADDR') or 'unknown'
    ip_allowed = _consume_rate_limit(_rate_key('ip', ip), limit, window)
    if not email_allowed or not ip_allowed:
        return None

    code = f'{secrets.randbelow(1_000_000):06d}'
    request.session['booking_request_data'] = booking_data
    request.session['booking_verify_hash'] = make_password(code)
    request.session['booking_verify_expires_at'] = int(time.time()) + _setting('BOOKING_OTP_TTL_SECONDS', 600)
    request.session['booking_verify_attempts'] = 0
    request.session.cycle_key()
    return code


def clear_booking_verification(request):
    for key in BOOKING_SESSION_KEYS:
        request.session.pop(key, None)


def check_booking_verification(request, entered_code):
    required = {'booking_request_data', 'booking_verify_hash', 'booking_verify_expires_at'}
    if not required.issubset(request.session.keys()):
        return 'missing'

    if int(request.session['booking_verify_expires_at']) < int(time.time()):
        clear_booking_verification(request)
        return 'expired'

    max_attempts = _setting('BOOKING_OTP_MAX_ATTEMPTS', 5)
    attempts = int(request.session.get('booking_verify_attempts', 0))
    if attempts >= max_attempts:
        clear_booking_verification(request)
        return 'locked'

    if not check_password((entered_code or '').strip(), request.session['booking_verify_hash']):
        attempts += 1
        request.session['booking_verify_attempts'] = attempts
        if attempts >= max_attempts:
            clear_booking_verification(request)
            return 'locked'
        return 'invalid'

    return 'verified'
