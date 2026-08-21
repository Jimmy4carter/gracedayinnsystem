# Verified Development and Launch Baseline

Baseline date: 2026-08-17

## Current checkpoint

- Django system check: passed with no issues.
- Production deployment check with Namecheap MariaDB configuration: passed. The only advisories are the intentionally deferred HSTS subdomain and preload flags; enable them only after every subdomain is permanently HTTPS.
- Migration consistency (`makemigrations --check --dry-run`): passed.
- Static collection: passed; the canonical public CSS, JavaScript and hotel logos are present in the collected output.
- Dependency integrity (`pip check`): passed.
- Dependency vulnerability audit (`pip-audit -r requirements.txt`): no known vulnerabilities.
- Static application security (`bandit -ll` excluding tests and migrations): no medium/high findings.
- System reconciliation: passed on the current local data with no pending migrations, booking/hold conflicts, missing payment/refund/folio/expenditure journals, unbalanced journals, expenditure total mismatch, missing expenditure status event, refund overage, negative stock balance or audit-chain variance.
- Full automated suite: 208 tests ran in 1277.515 seconds; 207 passed and the MariaDB-only multi-connection contention contract was intentionally skipped on local SQLite.
- Browser checks: public home, rooms, about, contact and billboard were inspected at desktop and 390 × 844 mobile. There was no horizontal overflow or broken imagery. WhatsApp was present, retired chat routes/UI were absent, and the billboard rendered 21 varied scenes with five randomly selected room scenes.

## Implemented launch foundation

- Transactional room search, availability holds, booking/OTP, reservation confirmation, invoices, VAT snapshots, the 50%-minimum check-in rule and guest/staff booking continuity.
- Cashier terminals and shifts, cash/POS reservation payments, A4 and thermal receipts, reprint audit evidence, append-only payment status events and balanced journals.
- Formal chart of accounts, journal lines, output/input VAT reporting, manager expenditure submission, independent accountant approval/payment, protected evidence, bank reconciliation, financial audit and Excel/PDF exports.
- Role-scoped administrator, manager, reception, accountant, housekeeping and guest portals; mandatory production staff MFA and six canonical deployment accounts.
- Brevo transactional delivery/contact/event logging with branded email templates and a configurable `noreply@gracedayinn.com` sender.
- Direct configurable WhatsApp support suitable for shared WSGI hosting; no active Channels, Daphne, Redis or WebSocket chat dependency.
- Namecheap Git deployment from the `production` branch, Passenger restart, MariaDB preflight, scheduled cron runner, encrypted database backup/verification and launch-readiness gates.

## Supported local setup

- Python 3.12
- Django 5.2.17
- Dependencies from `requirements.txt`
- SQLite for local development and MariaDB 11.4 in CI/production

Run the repeatable local gate:

```powershell
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test --noinput
python manage.py collectstatic --noinput
python manage.py reconcile_system --json
python -m pip check
```

Production and fresh-database CI additionally run `ensure_default_users`, `launch_readiness`, the MariaDB two-connection contention contract, `check --deploy`, Bandit and `pip-audit`.

## Scope and external launch gates

A green local baseline proves the implemented contracts and current local data are internally consistent. Final production acceptance still requires a green GitHub Actions run against MariaDB, cPanel environment/database/media/cron configuration, an encrypted backup and restore rehearsal, physical 58/80 mm printer certification, approved legal/brand/retention content, real-device user acceptance and operational sign-off.

The finance controls are bank-style internal controls, not a claim of bank certification or audited statutory accounts. A qualified accountant must approve the chart of accounts, VAT treatment, reporting basis and statutory procedures before live financial use.
