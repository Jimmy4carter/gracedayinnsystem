# GraceDay Inn hotel management system

GraceDay Inn is a Django 5.2 hotel website and property-management system. One transactional backend serves the public booking journey and the administrator, manager, reception, accountant, housekeeping, and guest portals.

Implemented operational areas include room categories/galleries/amenities, availability quotes and inventory holds, email-verified guest booking, reservations and stay changes, 50%-minimum check-in control, folios/invoices/VAT, cashier shifts and thermal receipts, append-only payment events and balanced journals, chart of accounts, controlled expenditure with maker/checker approval, input-VAT tracking, bank reconciliation, financial audits plus Excel/PDF reporting, housekeeping/maintenance/stock, services, inquiries and configurable WhatsApp contact, Brevo email/contact/event logging, management packs, role permissions/MFA, and reception billboard content.

## Local start

Prerequisites: Python 3.12 and `pip`.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

SQLite and console email are safe local defaults. Copy `.env.example` to the ignored `.env` only when you need local integration settings. Never commit credentials, generated accounts, databases, media, logs, or backup archives.

Create disposable local accounts for every role with unique generated passwords:

```powershell
python manage.py ensure_default_users --generate-missing
```

For production, supply all six `DEFAULT_*_PASSWORD` secrets instead; deployment never resets an existing usable password.

## Quality gate

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --noinput
python -m pip check
```

GitHub Actions additionally runs migrations and the concurrent-inventory contract on MariaDB 11.4, Django's production checks, Bandit, and `pip-audit`.

## Namecheap production

Production is deployed only from the `production` branch through cPanel Git Version Control, `.cpanel.yml`, Passenger WSGI, MariaDB/MySQL, WhiteNoise, persistent media, Brevo, and a five-minute cPanel cron. Routine releases do not require File Manager edits.

Start with:

- [deployment plan](docs/deployment_plan.md)
- [Git/cPanel release runbook](docs/28-namecheap-git-production-deployment.md)
- [production configuration](docs/12-production-configuration.md)
- [backup/restore](docs/17-backup-restore-runbook.md)
- [deployment/rollback](docs/18-deployment-rollback-runbook.md)
- [complete documentation index](docs/README.md)

Namecheap shared hosting runs WSGI rather than ASGI. Public support opens the hotel WhatsApp account directly, so deployment does not require Redis, Daphne, Channels, or WebSockets.

## Repository layout

- `apps/` — accounts, rooms, reservations, billing, payments, services, housekeeping, notifications, and frontend domains
- `gracedayinn/` — settings, URL routing, WSGI/ASGI entry points, and observability
- `deploy/` — cPanel deployment, preflight, and cron wrappers
- `docs/` — product, role, finance, security, launch, and operating runbooks
- `passenger_wsgi.py` — Namecheap Passenger entry point
