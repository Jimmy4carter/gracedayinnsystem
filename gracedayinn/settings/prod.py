import os

from django.core.exceptions import ImproperlyConfigured
from urllib.parse import urlparse

from .base import *


DEFAULT_USER_PASSWORD_VARIABLES = (
    'DEFAULT_ADMIN_PASSWORD', 'DEFAULT_MANAGER_PASSWORD', 'DEFAULT_RECEPTION_PASSWORD',
    'DEFAULT_ACCOUNTANT_PASSWORD', 'DEFAULT_HOUSEKEEPING_PASSWORD', 'DEFAULT_INFO_PASSWORD',
)


DEBUG = False

if SECRET_KEY.startswith('django-insecure-') or len(SECRET_KEY) < 40:
    raise ImproperlyConfigured('Production SECRET_KEY must be a strong environment secret.')
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured('Production ALLOWED_HOSTS must be configured.')
if DATABASES['default']['ENGINE'] not in {'django.db.backends.postgresql', 'django.db.backends.mysql'}:
    raise ImproperlyConfigured('Production requires a PostgreSQL or MySQL DATABASE_URL.')
EMAIL_DELIVERY_PROVIDER = EMAIL_DELIVERY_PROVIDER.strip().lower()
if EMAIL_DELIVERY_PROVIDER == 'brevo':
    if not BREVO_API_KEY:
        raise ImproperlyConfigured('Brevo REST delivery requires BREVO_API_KEY.')
elif EMAIL_DELIVERY_PROVIDER == 'brevo_smtp':
    smtp_backend = 'django.core.mail.backends.smtp.EmailBackend'
    if EMAIL_BACKEND != smtp_backend:
        raise ImproperlyConfigured(f'Brevo SMTP delivery requires EMAIL_BACKEND={smtp_backend}.')
    if not all((EMAIL_HOST, EMAIL_HOST_USER, EMAIL_HOST_PASSWORD)):
        raise ImproperlyConfigured(
            'Brevo SMTP delivery requires EMAIL_HOST, EMAIL_HOST_USER and EMAIL_HOST_PASSWORD.'
        )
    if EMAIL_HOST != 'smtp-relay.brevo.com':
        raise ImproperlyConfigured('Brevo SMTP EMAIL_HOST must be smtp-relay.brevo.com.')
    if EMAIL_PORT != 587 or not EMAIL_USE_TLS:
        raise ImproperlyConfigured('Brevo SMTP must use port 587 with EMAIL_USE_TLS=True.')
else:
    raise ImproperlyConfigured(
        "Production EMAIL_DELIVERY_PROVIDER must be 'brevo' or 'brevo_smtp'."
    )
if not BREVO_WEBHOOK_TOKEN:
    raise ImproperlyConfigured('Production requires BREVO_WEBHOOK_TOKEN.')
if not MFA_ENCRYPTION_KEY or len(MFA_ENCRYPTION_KEY) < 32:
    raise ImproperlyConfigured('Production requires MFA_ENCRYPTION_KEY with at least 32 characters.')
missing_default_passwords = [name for name in DEFAULT_USER_PASSWORD_VARIABLES if not os.environ.get(name)]
if missing_default_passwords:
    raise ImproperlyConfigured(
        'Production requires deployment account passwords: ' + ', '.join(missing_default_passwords)
    )

STAFF_MFA_REQUIRED = True

CSRF_TRUSTED_ORIGINS = config('CSRF_TRUSTED_ORIGINS', default='', cast=Csv())
CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', default='', cast=Csv())

SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = 'Lax'
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = 'Lax'
SECURE_SSL_REDIRECT = config('SECURE_SSL_REDIRECT', default=True, cast=bool)
SECURE_HSTS_SECONDS = config('SECURE_HSTS_SECONDS', default=31536000, cast=int)
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = 'same-origin'
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

EMAIL_OUTBOX_SEND_IMMEDIATELY = False
