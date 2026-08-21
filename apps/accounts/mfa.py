import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import timedelta
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import StaffMFADevice


STAFF_ROLES = {'admin', 'manager', 'receptionist', 'accountant', 'housekeeping'}


def _fernet():
    material = settings.MFA_ENCRYPTION_KEY or settings.SECRET_KEY
    key = base64.urlsafe_b64encode(hashlib.sha256(material.encode()).digest())
    return Fernet(key)


def _encrypt_secret(secret):
    return _fernet().encrypt(secret.encode())


def _decrypt_secret(device):
    try:
        return _fernet().decrypt(bytes(device.encrypted_secret)).decode()
    except InvalidToken as exc:
        raise ValidationError('The MFA secret cannot be decrypted with the configured key.') from exc


def _totp_at(secret, counter, digits=6):
    key = base64.b32decode(secret, casefold=True)
    digest = hmac.new(key, struct.pack('>Q', counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10 ** digits)).zfill(digits)


def current_totp(secret, at=None):
    return _totp_at(secret, int((at if at is not None else time.time()) // 30))


def staff_mfa_required(user):
    if not user or user.role not in STAFF_ROLES:
        return False
    device = StaffMFADevice.objects.filter(user=user, is_confirmed=True).exists()
    return bool(settings.STAFF_MFA_REQUIRED or device)


def begin_mfa_enrollment(*, user, actor=None):
    if user.role not in STAFF_ROLES:
        raise ValidationError('MFA enrollment is available only for staff accounts.')
    device = StaffMFADevice.objects.filter(user=user).first()
    if device and device.is_confirmed:
        raise ValidationError('MFA is already enabled for this account.')
    secret = _decrypt_secret(device) if device else base64.b32encode(secrets.token_bytes(20)).decode().rstrip('=')
    # Base32 length from 20 bytes needs no padding; keep generic decryption stable.
    if not device:
        device = StaffMFADevice.objects.create(user=user, encrypted_secret=_encrypt_secret(secret))
    issuer = quote(settings.MFA_ISSUER)
    account = quote(user.email or user.username)
    uri = f'otpauth://totp/{issuer}:{account}?secret={secret}&issuer={issuer}&digits=6&period=30'
    return device, secret, uri


def _matching_counter(secret, code, *, now=None):
    if not str(code).isdigit() or len(str(code)) != 6:
        return None
    counter = int((now if now is not None else time.time()) // 30)
    for candidate in (counter - 1, counter, counter + 1):
        if hmac.compare_digest(_totp_at(secret, candidate), str(code)):
            return candidate
    return None


def _new_recovery_codes():
    alphabet = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
    return [
        ''.join(secrets.choice(alphabet) for _ in range(4)) + '-' +
        ''.join(secrets.choice(alphabet) for _ in range(4))
        for _ in range(8)
    ]


def _record(action, user, actor=None, details=None):
    from apps.frontend.audit import record_audit_event
    record_audit_event(
        event_type='security', action=action, target_model='StaffMFADevice',
        target_id=user.id, actor=actor or user, details=details or {},
    )


@transaction.atomic
def confirm_mfa_enrollment(*, user, code, actor=None):
    device = StaffMFADevice.objects.select_for_update().filter(user=user, is_confirmed=False).first()
    if not device:
        raise ValidationError('No pending MFA enrollment exists.')
    counter = _matching_counter(_decrypt_secret(device), code)
    if counter is None:
        raise ValidationError('The authenticator code is invalid.')
    recovery_codes = _new_recovery_codes()
    device.is_confirmed = True
    device.confirmed_at = timezone.now()
    device.last_counter = counter
    device.recovery_code_hashes = [make_password(value) for value in recovery_codes]
    device.failed_attempts = 0
    device.locked_until = None
    device.save()
    _record('mfa_enrolled', user, actor, {'recovery_code_count': len(recovery_codes)})
    return device, recovery_codes


def verify_mfa_code(*, user, code, now=None):
    failure = None
    used_recovery = False
    with transaction.atomic():
        device = StaffMFADevice.objects.select_for_update().filter(user=user, is_confirmed=True).first()
        if not device:
            failure = 'MFA is not enrolled for this account.'
        elif device.locked_until and device.locked_until > timezone.now():
            failure = 'MFA verification is temporarily locked. Try again later.'
        else:
            secret = _decrypt_secret(device)
            counter = _matching_counter(secret, str(code).strip(), now=now)
            valid = counter is not None and counter > device.last_counter
            if valid:
                device.last_counter = counter
            else:
                for index, encoded in enumerate(device.recovery_code_hashes):
                    if check_password(str(code).strip().upper(), encoded):
                        device.recovery_code_hashes.pop(index)
                        used_recovery = valid = True
                        break
            if valid:
                device.failed_attempts = 0
                device.locked_until = None
                device.save(update_fields=[
                    'last_counter', 'recovery_code_hashes', 'failed_attempts',
                    'locked_until', 'updated_at',
                ])
            else:
                device.failed_attempts += 1
                if device.failed_attempts >= settings.MFA_MAX_ATTEMPTS:
                    device.locked_until = timezone.now() + timedelta(minutes=settings.MFA_LOCK_MINUTES)
                    device.failed_attempts = 0
                device.save(update_fields=['failed_attempts', 'locked_until', 'updated_at'])
                failure = 'The MFA code is invalid or has already been used.'
    if failure:
        _record('mfa_verification_failed', user, details={'locked': bool(device and device.locked_until)})
        raise ValidationError(failure)
    _record('mfa_verified', user, details={'recovery_code_used': used_recovery})
    return True


@transaction.atomic
def reset_mfa(*, user, actor, reason):
    if not reason.strip():
        raise ValidationError('A reason is required to reset MFA.')
    if not (actor.is_superuser or actor.role == 'admin'):
        raise ValidationError('Only an administrator can reset MFA.')
    StaffMFADevice.objects.filter(user=user).delete()
    _record('mfa_reset', user, actor, {'reason': reason.strip()})
