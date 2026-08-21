import secrets

from decouple import config
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction


DEFAULT_USERS = (
    {'username': 'admin', 'email': 'admin@gracedayinn.com', 'role': 'admin', 'first_name': 'System', 'last_name': 'Administrator', 'env': 'DEFAULT_ADMIN_PASSWORD', 'superuser': True},
    {'username': 'manager', 'email': 'manager@gracedayinn.com', 'role': 'manager', 'first_name': 'Hotel', 'last_name': 'Manager', 'env': 'DEFAULT_MANAGER_PASSWORD'},
    {'username': 'reception', 'email': 'reception@gracedayinn.com', 'role': 'receptionist', 'first_name': 'Front', 'last_name': 'Desk', 'env': 'DEFAULT_RECEPTION_PASSWORD'},
    {'username': 'accountant', 'email': 'accounts@gracedayinn.com', 'role': 'accountant', 'first_name': 'Hotel', 'last_name': 'Accounts', 'env': 'DEFAULT_ACCOUNTANT_PASSWORD'},
    {'username': 'housekeeping', 'email': 'housekeeping@gracedayinn.com', 'role': 'housekeeping', 'first_name': 'Housekeeping', 'last_name': 'Team', 'env': 'DEFAULT_HOUSEKEEPING_PASSWORD'},
    {'username': 'info', 'email': 'info@gracedayinn.com', 'role': 'guest', 'first_name': 'GraceDay', 'last_name': 'Information', 'env': 'DEFAULT_INFO_PASSWORD'},
)


def generated_password():
    return f'{secrets.token_urlsafe(18)}!Gd9'


@transaction.atomic
def ensure_default_users(*, generate_missing=False):
    User = get_user_model()
    from .models import GuestProfile

    configured_roles = {item['role'] for item in DEFAULT_USERS}
    model_roles = {value for value, _label in User.ROLE_CHOICES}
    if configured_roles != model_roles:
        missing = sorted(model_roles - configured_roles)
        extra = sorted(configured_roles - model_roles)
        raise ValidationError(
            f'Default account roles do not match the user model; missing={missing}, extra={extra}.'
        )
    results = []
    for definition in DEFAULT_USERS:
        password = config(definition['env'], default='')
        generated = False
        if not password and generate_missing:
            password, generated = generated_password(), True
        if not password:
            results.append({**definition, 'status': 'skipped', 'password': ''})
            continue
        candidate = User(username=definition['username'], email=definition['email'])
        try:
            validate_password(password, user=candidate)
        except ValidationError as exc:
            raise ValidationError(f"{definition['env']}: {'; '.join(exc.messages)}") from exc
        user, created = User.objects.get_or_create(
            username=definition['username'],
            defaults={
                'email': definition['email'], 'role': definition['role'],
                'first_name': definition['first_name'], 'last_name': definition['last_name'],
                'is_active': True,
                'is_staff': definition['role'] != 'guest',
                'is_superuser': definition.get('superuser', False),
            },
        )
        changed = created
        for field, value in {
            'email': definition['email'], 'role': definition['role'],
            'first_name': definition['first_name'], 'last_name': definition['last_name'],
            'is_active': True, 'is_staff': definition['role'] != 'guest',
            'is_superuser': definition.get('superuser', False),
        }.items():
            if getattr(user, field) != value:
                setattr(user, field, value)
                changed = True
        if created or not user.has_usable_password():
            user.set_password(password)
            changed = True
        if changed:
            user.save()
        if definition['role'] == 'guest':
            GuestProfile.objects.get_or_create(user=user)
        results.append({**definition, 'status': 'created' if created else 'verified', 'password': password if generated else ''})
    return results
