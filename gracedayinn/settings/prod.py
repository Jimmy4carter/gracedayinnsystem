from django.core.exceptions import ImproperlyConfigured
from urllib.parse import urlparse

from .base import *


DEBUG = False

if SECRET_KEY.startswith('django-insecure-') or len(SECRET_KEY) < 40:
    raise ImproperlyConfigured('Production SECRET_KEY must be a strong environment secret.')
if not ALLOWED_HOSTS:
    raise ImproperlyConfigured('Production ALLOWED_HOSTS must be configured.')
if DATABASES['default']['ENGINE'] not in {'django.db.backends.postgresql', 'django.db.backends.mysql'}:
    raise ImproperlyConfigured('Production requires a PostgreSQL or MySQL DATABASE_URL.')
if EMAIL_DELIVERY_PROVIDER != 'brevo' or not BREVO_API_KEY:
    raise ImproperlyConfigured('Production requires Brevo email delivery and BREVO_API_KEY.')
if not BREVO_WEBHOOK_TOKEN:
    raise ImproperlyConfigured('Production requires BREVO_WEBHOOK_TOKEN.')
if not MFA_ENCRYPTION_KEY or len(MFA_ENCRYPTION_KEY) < 32:
    raise ImproperlyConfigured('Production requires MFA_ENCRYPTION_KEY with at least 32 characters.')

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
