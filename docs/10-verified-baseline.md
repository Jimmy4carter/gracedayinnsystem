# Verified Development Baseline

Baseline date: 2026-08-10

## Current checkpoint

- Django system check: passed.
- Production deployment check with PostgreSQL configuration: passed.
- Migration consistency (`makemigrations --check --dry-run`): passed.
- Dependency integrity (`pip check`): passed.
- Dependency vulnerability audit (`pip-audit -r requirements.txt`): no known vulnerabilities after upgrading to Django 5.2.17.
- System reconciliation: passed with no pending migration, inventory conflict, unledgered completed payment, refund overage, negative stock balance or audit-chain variance. Two legacy completed payments were backfilled idempotently into folios by `payments.0004`.
- Full automated suite under Django 5.2.17: 186 tests ran in 684.158 seconds; 185 passed and the real PostgreSQL multi-connection contention contract was intentionally skipped on local SQLite. Coverage includes OTLP trace/log correlation, Brevo SSRF/redirect boundaries, migration/system reconciliation, idempotent legacy-payment ledger backfill, route-wide portal/API authorization and controlled exports, governed FAQ/policy approval and draft isolation, public-search privacy, keyboard-first front-desk navigation, immutable operational and financial ledgers, controlled incident/lost-item lifecycles, managed room galleries, encrypted staff MFA, JWT revocation, tamper-evident audit verification, privacy governance, public quality gates, live-chat controls and operational escalation.
- Static application security (`bandit -ll` excluding test/migration fixtures): no medium/high findings after hardening Brevo HTTPS and redirect validation.
- Live telemetry smoke: the OpenTelemetry-wrapped Django/ASGI server exported a valid `/health/live/` server span with route/status, service identity and SDK/auto-instrumentation versions while preserving the supplied request ID.
- Focused inventory/extras/guest-identity suite: 10 tests passed in 21.297 seconds; commercial suite: 5 tests passed; reporting/worker suite: 8 tests passed; focused frontend/public suite: 38 tests passed.
- Rendered browser checks: homepage, rooms and room-detail handoff plus itemized quote review at desktop and 390 px mobile widths; no console warnings/errors observed.
- Covered foundations now include centralized authorization; secure onboarding and mandatory production staff MFA; short-lived JWTs with rotating, revocable refresh tokens; transactional inventory/occupancy rates/quotes/holds; date-bound sellable inventory; taxable bookable extras; audited guest deduplication; immutable folios and manager-authorized corrections; ledger tax summaries; cashiering/POS; a verified booking-to-checkout/shift-close journey; audited print failure/retry plus A4/58/80 mm document contracts; front-desk stay management; housekeeping/maintenance; Brevo-logged email and contact synchronization; SLA-routed inquiries with protected evidence; business-hours-aware live chat; management reporting/night audit; guest self-service; governed public FAQs and version-approved policies; public SEO/accessibility/privacy controls; encrypted PostgreSQL backup verification; role-specific operational runbooks; correlated JSON request logs; and dependency readiness probes.

## Supported local setup

- Python 3.12.4
- Project-local virtual environment: `.venv`
- Dependencies installed from `requirements.txt`
- Django 5.2.17
- Development database: SQLite

Activate the environment in PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

## Baseline commands

Run these before beginning a feature and before handing it off:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test
```

Optional dependency verification:

```powershell
.\.venv\Scripts\python.exe -m pip check
```

## Repairs made to establish the baseline

- Corrected the invalid `AbstractUser` import in `apps/accounts/models.py` that prevented Django from loading.
- Rebuilt `.venv`, which referenced a removed Microsoft Store Python installation.
- Added standard local/generated Python paths to `.gitignore`.
- Updated the service-order lifecycle test to submit the username expected by `ServiceOrderCreateForm`; the test had retained the obsolete numeric guest-ID contract.

## Scope and limitations

A green baseline means the implemented behavior is internally consistent. Launch acceptance still requires staging PostgreSQL concurrency/migration and backup-restore rehearsals, physical printer certification, owner-approved legal/brand content, provider credentials, UAT/training and operational sign-off recorded in the master backlog.
