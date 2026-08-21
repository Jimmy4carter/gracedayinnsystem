from pathlib import Path
from decouple import config, Csv
import os
from urllib.parse import parse_qs, unquote, urlparse

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config('SECRET_KEY', default='django-insecure-graceday-inn-secret-key-change-in-production')
DEBUG = config('DEBUG', default=True, cast=bool)
ALLOWED_HOSTS = config('ALLOWED_HOSTS', default='localhost,127.0.0.1', cast=Csv())

DJANGO_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]

THIRD_PARTY_APPS = [
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',
    'django_filters',
]

LOCAL_APPS = [
    'apps.accounts.apps.AccountsConfig',
    'apps.rooms.apps.RoomsConfig',
    'apps.reservations.apps.ReservationsConfig',
    'apps.billing.apps.BillingConfig',
    'apps.payments.apps.PaymentsConfig',
    'apps.services.apps.ServicesConfig',
    'apps.housekeeping.apps.HousekeepingConfig',
    'apps.notifications.apps.NotificationsConfig',
    'apps.frontend.apps.FrontendConfig',
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'gracedayinn.observability.RequestObservabilityMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'apps.accounts.middleware.StaffMFASessionMiddleware',
    'apps.frontend.audit.AuthenticatedMutationAuditMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

LOGGING = {
    'version': 1, 'disable_existing_loggers': False,
    'formatters': {'json': {'()': 'gracedayinn.observability.JsonLogFormatter'}},
    'handlers': {'console_json': {'class': 'logging.StreamHandler', 'formatter': 'json'}},
    'loggers': {
        'gracedayinn.request': {
            'handlers': ['console_json'], 'level': 'INFO' if not DEBUG else 'WARNING',
            'propagate': False,
        },
    },
}

ROOT_URLCONF = 'gracedayinn.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'apps' / 'frontend' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'apps.frontend.context_processors.public_site_page',
            ],
        },
    },
]

WSGI_APPLICATION = 'gracedayinn.wsgi.application'
ASGI_APPLICATION = 'gracedayinn.asgi.application'

DATABASE_URL = config('DATABASE_URL', default='')
if DATABASE_URL:
    parsed_database = urlparse(DATABASE_URL)
    if parsed_database.scheme in {'postgres', 'postgresql'}:
        database_options = {}
        sslmode = parse_qs(parsed_database.query).get('sslmode', [None])[0]
        if sslmode:
            database_options['sslmode'] = sslmode
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.postgresql',
                'NAME': unquote(parsed_database.path.lstrip('/')),
                'USER': unquote(parsed_database.username or ''),
                'PASSWORD': unquote(parsed_database.password or ''),
                'HOST': parsed_database.hostname or '',
                'PORT': parsed_database.port or 5432,
                'CONN_MAX_AGE': config('DB_CONN_MAX_AGE', default=60, cast=int),
                'CONN_HEALTH_CHECKS': True,
                'OPTIONS': database_options,
            }
        }
    elif parsed_database.scheme in {'mysql', 'mysql2'}:
        DATABASES = {
            'default': {
                'ENGINE': 'django.db.backends.mysql',
                'NAME': unquote(parsed_database.path.lstrip('/')),
                'USER': unquote(parsed_database.username or ''),
                'PASSWORD': unquote(parsed_database.password or ''),
                'HOST': parsed_database.hostname or '',
                'PORT': parsed_database.port or 3306,
                'CONN_MAX_AGE': config('DB_CONN_MAX_AGE', default=60, cast=int),
                'CONN_HEALTH_CHECKS': True,
                'OPTIONS': {
                    'charset': 'utf8mb4',
                    'connect_timeout': config('DB_CONNECT_TIMEOUT', default=10, cast=int),
                    'init_command': "SET sql_mode='STRICT_TRANS_TABLES'",
                    'isolation_level': 'read committed',
                },
            }
        }
    elif parsed_database.scheme == 'sqlite':
        sqlite_path = parsed_database.path.lstrip('/') or 'db.sqlite3'
        DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / sqlite_path}}
    else:
        raise ValueError('DATABASE_URL must use postgresql://, mysql:// or sqlite:///')
else:
    DATABASES = {'default': {'ENGINE': 'django.db.backends.sqlite3', 'NAME': BASE_DIR / 'db.sqlite3'}}

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

LANGUAGE_CODE = 'en-us'
TIME_ZONE = config('TIME_ZONE', default='Africa/Lagos')
USE_I18N = True
USE_TZ = True

STATIC_URL = '/static/'
STATIC_ROOT = Path(config('STATIC_ROOT', default=str(BASE_DIR / 'collected_static')))
STATICFILES_DIRS = [
    ('css', BASE_DIR / 'staticfiles' / 'css'),
    ('fonts', BASE_DIR / 'staticfiles' / 'fonts'),
    ('img', BASE_DIR / 'staticfiles' / 'img'),
    ('js', BASE_DIR / 'staticfiles' / 'js'),
]
STATICFILES_FINDERS = [
    'gracedayinn.staticfiles.PortablePrefixedFileSystemFinder',
    'django.contrib.staticfiles.finders.AppDirectoriesFinder',
]
STORAGES = {
    'default': {'BACKEND': 'django.core.files.storage.FileSystemStorage'},
    # The legacy vendor bundle includes third-party source-map comments whose map files are
    # absent. Compression is safe here; manifest rewriting would make collectstatic fail.
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedStaticFilesStorage'},
}

MEDIA_URL = '/media/'
MEDIA_ROOT = Path(config('MEDIA_ROOT', default=str(BASE_DIR / 'media')))

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'
AUTH_USER_MODEL = 'accounts.UserProfile'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
        'rest_framework.authentication.SessionAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

from datetime import timedelta
SIMPLE_JWT = {
    'ACCESS_TOKEN_LIFETIME': timedelta(minutes=15),
    'REFRESH_TOKEN_LIFETIME': timedelta(days=7),
    'ROTATE_REFRESH_TOKENS': True,
    'BLACKLIST_AFTER_ROTATION': True,
    'UPDATE_LAST_LOGIN': True,
}

CORS_ALLOWED_ORIGINS = [
    'http://localhost:8000',
    'http://127.0.0.1:8000',
]
CORS_ALLOW_CREDENTIALS = True

EMAIL_BACKEND = config(
    'EMAIL_BACKEND', default='django.core.mail.backends.console.EmailBackend'
)
EMAIL_HOST = config('EMAIL_HOST', default='smtp-relay.brevo.com')
EMAIL_PORT = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = config('EMAIL_USE_TLS', default=True, cast=bool)
EMAIL_TIMEOUT = config('EMAIL_TIMEOUT', default=20, cast=int)
DEFAULT_FROM_EMAIL = config('DEFAULT_FROM_EMAIL', default='noreply@gracedayinn.com')
SERVER_EMAIL = config('SERVER_EMAIL', default=DEFAULT_FROM_EMAIL)
HOTEL_CURRENCY = config('HOTEL_CURRENCY', default='NGN')

BOOKING_OTP_TTL_SECONDS = config('BOOKING_OTP_TTL_SECONDS', default=600, cast=int)
BOOKING_OTP_MAX_ATTEMPTS = config('BOOKING_OTP_MAX_ATTEMPTS', default=5, cast=int)
BOOKING_OTP_SEND_LIMIT = config('BOOKING_OTP_SEND_LIMIT', default=5, cast=int)
BOOKING_OTP_SEND_WINDOW_SECONDS = config('BOOKING_OTP_SEND_WINDOW_SECONDS', default=3600, cast=int)
PASSWORD_RESET_TIMEOUT = config('PASSWORD_SETUP_TIMEOUT_SECONDS', default=86400, cast=int)
LOGIN_FAILURE_LIMIT = config('LOGIN_FAILURE_LIMIT', default=5, cast=int)
LOGIN_FAILURE_WINDOW_SECONDS = config('LOGIN_FAILURE_WINDOW_SECONDS', default=900, cast=int)
STAFF_MFA_REQUIRED = config('STAFF_MFA_REQUIRED', default=False, cast=bool)
MFA_ENCRYPTION_KEY = config('MFA_ENCRYPTION_KEY', default='')
MFA_ISSUER = config('MFA_ISSUER', default='GraceDay Inn')
MFA_MAX_ATTEMPTS = config('MFA_MAX_ATTEMPTS', default=5, cast=int)
MFA_LOCK_MINUTES = config('MFA_LOCK_MINUTES', default=15, cast=int)
CASH_VARIANCE_APPROVAL_THRESHOLD = config(
    'CASH_VARIANCE_APPROVAL_THRESHOLD', default='1000.00'
)
EMAIL_DELIVERY_PROVIDER = config('EMAIL_DELIVERY_PROVIDER', default='django')
EMAIL_OUTBOX_SEND_IMMEDIATELY = config('EMAIL_OUTBOX_SEND_IMMEDIATELY', default=True, cast=bool)
EMAIL_OUTBOX_MAX_ATTEMPTS = config('EMAIL_OUTBOX_MAX_ATTEMPTS', default=5, cast=int)
BREVO_API_KEY = config('BREVO_API_KEY', default='')
BREVO_WEBHOOK_TOKEN = config('BREVO_WEBHOOK_TOKEN', default='')
BREVO_SENDER_NAME = config('BREVO_SENDER_NAME', default='GRACEDAY INN')
BREVO_SANDBOX = config('BREVO_SANDBOX', default=False, cast=bool)
BREVO_CONTACT_LIST_ID = config('BREVO_CONTACT_LIST_ID', default=0, cast=int)
OTEL_EXPORTER_OTLP_ENDPOINT = config('OTEL_EXPORTER_OTLP_ENDPOINT', default='')
OTEL_SERVICE_NAME = config('OTEL_SERVICE_NAME', default='graceday-inn')
RELEASE_VERSION = config('RELEASE_VERSION', default='development')

import sys
if 'test' in sys.argv or 'test_coverage' in sys.argv:
    # Never let a developer's local Brevo credentials turn automated tests into real email sends.
    EMAIL_DELIVERY_PROVIDER = 'django'
    EMAIL_OUTBOX_SEND_IMMEDIATELY = True
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
            'LOCATION': 'test-cache-snowflake',
        }
    }
else:
    CACHES = {
        'default': {
            'BACKEND': 'django.core.cache.backends.db.DatabaseCache',
            'LOCATION': 'graceday_cache_table',
        }
    }

WHATSAPP_NUMBER = config('WHATSAPP_NUMBER', default='2347080076496')
WHATSAPP_DEFAULT_MESSAGE = config(
    'WHATSAPP_DEFAULT_MESSAGE',
    default='Hello GraceDay Inn, I would like help with a reservation.',
)

LOGIN_URL = '/portal/sign-in/'
LOGIN_REDIRECT_URL = '/portal/dashboard/'
LOGOUT_REDIRECT_URL = '/portal/sign-in/'
