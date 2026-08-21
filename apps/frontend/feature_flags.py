from django.db import OperationalError, ProgrammingError

from .models import FeatureFlag


def flag_enabled(key, *, user=None, default=False):
    try:
        flag = FeatureFlag.objects.filter(key=key).first()
    except (OperationalError, ProgrammingError):
        return default
    if not flag:
        return default
    if not flag.is_enabled:
        return False
    if not flag.roles:
        return True
    role = getattr(user, 'role', None) if user and user.is_authenticated else 'anonymous'
    return role in flag.roles
