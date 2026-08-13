# Production Configuration

Use `gracedayinn.settings.prod` in production. This module fails closed when the secret, hosts or PostgreSQL database are missing.

Production additionally requires Redis, Brevo and an OTLP collector: set `REDIS_URL`, `EMAIL_DELIVERY_PROVIDER=brevo`, `BREVO_API_KEY`, a strong `BREVO_WEBHOOK_TOKEN`, `OTEL_EXPORTER_OTLP_ENDPOINT` and the immutable release identifier. Run the ASGI process through OpenTelemetry as shown below; WSGI alone cannot serve live chat. Run `manage.py run_scheduled_jobs` every minute from the hosting scheduler; database claiming prevents duplicate execution across overlapping workers.

Configure liveness at `/health/live/` and readiness at `/health/ready/`. Readiness returns HTTP 503 when PostgreSQL, Redis/cache or scheduler freshness fails. Ship JSON stdout logs to the deployment log/error platform and preserve `X-Request-ID` in proxy logs.

## Required environment

```env
DJANGO_SETTINGS_MODULE=gracedayinn.settings.prod
SECRET_KEY=<at-least-40-character-random-secret>
ALLOWED_HOSTS=hotel.example.com
DATABASE_URL=postgresql://user:password@db:5432/gracedayinn?sslmode=require
CSRF_TRUSTED_ORIGINS=https://hotel.example.com
CORS_ALLOWED_ORIGINS=https://hotel.example.com
REDIS_URL=rediss://default:<password>@redis.example.com:6379/0
EMAIL_DELIVERY_PROVIDER=brevo
BREVO_API_KEY=<deployment-secret>
BREVO_WEBHOOK_TOKEN=<at-least-32-character-random-secret>
MFA_ENCRYPTION_KEY=<unique-random-secret-at-least-32-characters>
OTEL_EXPORTER_OTLP_ENDPOINT=https://otel-collector.example.com
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
OTEL_EXPORTER_OTLP_HEADERS=<secret-manager-supplied-auth-header-if-required>
OTEL_SERVICE_NAME=graceday-inn
OTEL_RESOURCE_ATTRIBUTES=deployment.environment.name=production,service.version=<release-id>
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=0.1
RELEASE_VERSION=<immutable-image-or-git-release-id>
BREVO_CONTACT_LIST_ID=<numeric-marketing-list-id-or-0>
BACKUP_ENCRYPTION_KEY=<secret-manager-value-at-least-24-characters>
EMAIL_HOST=smtp-relay.brevo.com
EMAIL_PORT=587
EMAIL_HOST_USER=<brevo-smtp-user>
EMAIL_HOST_PASSWORD=<deployment-secret>
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=reservations@hotel.example.com
HOTEL_CURRENCY=NGN
TIME_ZONE=Africa/Lagos
```

Start the ASGI service with vendor-neutral OpenTelemetry instrumentation:

```powershell
opentelemetry-instrument daphne -b 0.0.0.0 -p 8000 gracedayinn.asgi:application
```

This exports Django/ASGI, PostgreSQL, Redis and outbound HTTP traces and metrics over OTLP. Structured application logs include the same 32-character trace ID, span ID and immutable release. Keep collector authentication in the secret manager, never in source or ordinary logs.

## Release checks

```powershell
python manage.py check --deploy --settings=gracedayinn.settings.prod
python manage.py migrate --plan --settings=gracedayinn.settings.prod
python manage.py migrate --settings=gracedayinn.settings.prod
python manage.py collectstatic --noinput --settings=gracedayinn.settings.prod
python manage.py run_scheduled_jobs --limit 20 --settings=gracedayinn.settings.prod
```

Apply database migrations using one release job before bringing new application instances into service. Take and verify a PostgreSQL backup before migrations that transform existing data.

## Current migration boundary

Migration `reservations.0002_add_reservation_history_and_snapshots` adds reservation snapshots and append-only history, then backfills all existing reservations. Reconcile these values after staging migration:

- reservation count before and after;
- every reservation has at least one status-history row;
- every reservation has a room-assignment row;
- every reservation has a non-empty price snapshot;
- totals grouped by status and source match expected legacy totals.

The project is configured for PostgreSQL, but production readiness still requires a staging migration, backup restore, rollback decision rehearsal and true concurrent booking test against the selected hosted PostgreSQL service.
