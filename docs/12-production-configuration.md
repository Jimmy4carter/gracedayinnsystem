# Production configuration — Namecheap shared hosting

GraceDay Inn production runs with `gracedayinn.settings.prod`, Passenger WSGI, and the MySQL-compatible MariaDB service supplied by Namecheap. The settings fail closed if the host, database, Brevo, MFA, or deployment-account secrets are incomplete.

## Required environment

Keep these values in cPanel **Setup Python App > Environment variables** or the ignored server `.env`. Never commit real values.

```env
DJANGO_SETTINGS_MODULE=gracedayinn.settings.prod
SECRET_KEY=<unique-random-value-at-least-40-characters>
ALLOWED_HOSTS=gracedayinn.com,www.gracedayinn.com
CSRF_TRUSTED_ORIGINS=https://gracedayinn.com,https://www.gracedayinn.com
CORS_ALLOWED_ORIGINS=https://gracedayinn.com,https://www.gracedayinn.com
DATABASE_URL=mysql://CPANEL_DB_USER:URL_ENCODED_PASSWORD@127.0.0.1:3306/CPANEL_DB_NAME
DB_CONNECT_TIMEOUT=10

EMAIL_DELIVERY_PROVIDER=brevo
BREVO_API_KEY=<new-production-rest-api-key>
BREVO_WEBHOOK_TOKEN=<unique-random-webhook-token>
BREVO_CONTACT_LIST_ID=0
BREVO_SANDBOX=False
DEFAULT_FROM_EMAIL=noreply@gracedayinn.com
SERVER_EMAIL=noreply@gracedayinn.com
WHATSAPP_NUMBER=2347080076496
WHATSAPP_DEFAULT_MESSAGE=Hello GraceDay Inn, I would like help with a reservation.

MFA_ENCRYPTION_KEY=<unique-random-value-at-least-32-characters>
DEFAULT_ADMIN_PASSWORD=<unique-generated-secret>
DEFAULT_MANAGER_PASSWORD=<unique-generated-secret>
DEFAULT_RECEPTION_PASSWORD=<unique-generated-secret>
DEFAULT_ACCOUNTANT_PASSWORD=<unique-generated-secret>
DEFAULT_HOUSEKEEPING_PASSWORD=<unique-generated-secret>
DEFAULT_INFO_PASSWORD=<unique-generated-secret>

MEDIA_ROOT=/home/CPANEL_USERNAME/gracedayinn_media
STATIC_ROOT=/home/CPANEL_USERNAME/gracedayinnsystem/collected_static
BACKUP_ENCRYPTION_KEY=<separate-unique-secret-at-least-24-characters>
HOTEL_CURRENCY=NGN
TIME_ZONE=Africa/Lagos
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=3600
SECURE_HSTS_INCLUDE_SUBDOMAINS=False
SECURE_HSTS_PRELOAD=False
RELEASE_VERSION=<git-commit-sha>
```

REST delivery is the preferred Brevo mode because transactional delivery, contact synchronization, event logging, and newsletter operations then use one controlled integration. SMTP remains supported with `EMAIL_DELIVERY_PROVIDER=brevo_smtp`, the Django SMTP backend, TLS port 587, and SMTP credentials, but `BREVO_API_KEY` is still required for contact sync and reporting.

The six deployment passwords create or verify exactly one canonical account for every role. Existing usable passwords are never reset by deployment. Store each initial password separately, sign in once, enroll staff MFA, and rotate it. Do not put shared or predictable passwords in source.

## Shared-hosting runtime

Create the Python application with:

| cPanel field | Value |
| --- | --- |
| Python | 3.12 |
| Application root | `gracedayinnsystem` |
| Startup file | `app.py` |
| Entry point | `application` |

CloudLinux requires a startup filename and callable. Keep `app.py` separate from the generated `passenger_wsgi.py`; selecting `passenger_wsgi.py` as its own startup file can make cPanel generate a self-referencing wrapper. The deployment hook verifies that `app.application` imports successfully before applying migrations.

Namecheap shared hosting serves WSGI, not ASGI. The public site uses a direct configurable WhatsApp action, so the production application has no WebSocket, Redis, Daphne, or live-chat runtime dependency.

The database connection uses `utf8mb4`, strict transaction mode, `READ COMMITTED`, connection health checks, and InnoDB-compatible transactional operations. SQLite is development-only and production rejects it.

## Release and readiness gates

The committed `.cpanel.yml` invokes `deploy/namecheap_deploy.sh`. The hook verifies the `production` branch, prevents overlapping deployments, installs dependencies, runs deployment and migration-drift checks, collects static files, previews and applies migrations, creates the database cache table, verifies canonical users, runs launch readiness/reconciliation, and restarts Passenger.

For a manual preflight after configuring the server:

```bash
cd /home/CPANEL_USERNAME/gracedayinnsystem
GRACEDAY_PYTHON=/home/CPANEL_USERNAME/virtualenv/gracedayinnsystem/3.12/bin/python \
  bash deploy/namecheap_preflight.sh
```

For a complete post-migration gate:

```bash
python manage.py ensure_default_users
python manage.py launch_readiness --prepare-storage
python manage.py reconcile_system --json
```

`launch_readiness` checks the actual MariaDB connection and strict mode, all role accounts, the formal chart of accounts, expense categories, cashier terminal, WhatsApp contact, cache read/write, required scheduled jobs, Brevo configuration, writable static/media paths, migrations, inventory conflicts, payment/folio/expenditure integrity, refund overages, balanced journals, stock balances, and the tamper-evident audit chain.

## Scheduler and health

Run `manage.py run_scheduled_jobs` every five minutes from cPanel cron. This processes the email outbox, Brevo contacts, expired holds, manager packs, and operational alerts without a persistent worker process.

Use `/health/live/` for process health and `/health/ready/` for dependency/scheduler readiness. Preserve `X-Request-ID` in server logs. `OTEL_EXPORTER_OTLP_ENDPOINT` is optional on shared hosting; correlated structured application logging remains available without a collector.
