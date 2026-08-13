# Quality, Security and Operations Plan

## Test strategy

### Unit and domain tests

- Availability, holds, pricing, taxes, policies, money rounding and occupancy rules.
- Every reservation/stay/payment/task/query state transition including invalid transitions.
- Folio balance, reversals, partial/split settlement, refund and cashier variance.
- Permission policy across role, property scope, ownership, thresholds and approval separation.

### Integration tests

- PostgreSQL constraints/locking with real concurrent transactions.
- Celery/outbox retries, Redis behavior, Brevo adapter/webhooks, payment provider and object storage.
- PDF/receipt generation and deterministic data snapshots.
- Migration/backfill and reconciliation tests on anonymized production-like volume.

### End-to-end tests

- Public search -> booking -> payment -> confirmation -> guest portal.
- Walk-in -> deposit -> check-in -> service charge -> split settlement -> thermal receipt -> checkout.
- Cashier shift open -> movements -> count -> variance approval -> close/Z report.
- Checkout -> dirty room -> housekeeping -> inspection -> available.
- Inquiry/chat -> assignment -> reservation link -> resolution.
- Management metric -> drill-down -> query -> response -> resolution.

### Experience tests

- WCAG 2.2 AA automation plus keyboard/screen-reader manual review.
- Responsive and cross-browser matrix; slow-network and low-spec front-desk hardware.
- Agreed thermal printer models using real paper, long names, many items, reprints and offline/failure scenarios.
- Load tests for availability search, booking contention, dashboard/report queries and chat concurrency.

## Security controls

- Threat model public booking, authentication, staff portals, APIs, WebSockets, exports, webhooks, printer bridge and admin actions.
- Enforce least privilege and object scope server-side; automated regression matrix.
- CSRF, secure/HttpOnly/SameSite cookies, HSTS, CSP, clickjacking protection, restricted CORS and trusted origins.
- Rate limits and bot controls on login, reset, OTP, availability, booking, inquiry and chat.
- Re-authentication/MFA for role changes, integrations, large refunds/discounts and sensitive exports.
- Encrypt traffic; protect backups/object storage; redact secrets, tokens and unnecessary personal data from logs.
- Validate uploads by size/type/content, malware-scan where required, store privately and serve with expiring authorization.
- Pin/scan dependencies, review licenses/vendor static assets, rotate secrets and maintain a vulnerability response process.
- External security assessment before launch and after material payment/auth architecture changes.

## Privacy and governance

- Create a data inventory and classify contact, identity, financial, chat, device and audit data.
- Define lawful purpose/consent with qualified advisers for applicable Nigeria Data Protection Act and other obligations.
- Separate essential transactional communications from marketing preferences.
- Implement access/export, correction, retention, legal hold and deletion/anonymization workflows.
- Avoid storing identity-document images unless there is a confirmed requirement, protected access and retention rule.
- Restrict management reports and exports to the minimum personal data required.

## Observability

- Structured JSON logs with request/trace ID, actor ID, property, command and outcome; redact sensitive fields.
- Metrics: request latency/error, DB/worker/queue, booking conflicts, payment mismatches, email failures, WebSocket connections, report duration and print failures.
- Business health: booking funnel, pending payments, unreconciled tenders, room-state conflicts, overdue inquiries/tasks and cashier variances.
- Error tracking with release tags and source maps where applicable.
- Alerts must have owner, severity, response target and linked runbook; avoid alerting on unactionable noise.

## Deployment and environments

- Local, test, staging and production configurations with no production secrets/data committed.
- CI gates: Django checks, migration/reconciliation checks, PostgreSQL contention, full domain/permission/integration tests, production configuration, medium/high-confidence Bandit static analysis and live dependency vulnerability audit. Deployment artifact construction remains hosting-platform specific.
- Immutable releases, database migration plan, feature flags, health probes, smoke tests and rollback procedure.
- Staging should closely mirror production and use synthetic/anonymized data.
- Zero/low-downtime migrations use expand/backfill/switch/contract steps.

## Backup and recovery

- Automated encrypted PostgreSQL backups plus point-in-time recovery if supported; versioned object storage backup/retention.
- Separate backup credentials and access; monitor backup completion.
- Proposed V1 objectives: RPO 15 minutes, RTO 4 hours, subject to business approval.
- Restore into an isolated environment at least quarterly and reconcile counts, financial totals and representative documents.
- Document disaster declaration, communication, restore, verification and return-to-service ownership.

## Operational runbooks required

- Deployment/rollback, failed migration, database saturation, worker/Redis outage.
- Brevo/payment/webhook outage and reconciliation.
- Booking conflict, incorrect room state, stuck night audit and failed scheduled report.
- Printer failure and manual receipt contingency.
- Suspected account compromise/data incident and credential rotation.
- Backup restore and post-restore reconciliation.

## Production readiness gate

- No open P0 issues; P1 exceptions have named owner and accepted mitigation.
- UAT signed by front desk, cashier/finance, housekeeping, management and website owner.
- Permission matrix, financial reconciliation, concurrency and restore tests pass.
- Monitoring/alerts/runbooks/on-call contacts are active.
- Staff training, least-privilege accounts, terminal/printer configuration and go-live support are complete.
