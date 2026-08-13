# Master Backlog

Statuses: `[ ]` not started, `[~]` active, `[x]` accepted. Priority: P0 critical, P1 launch-essential, P2 valuable follow-up.

## Foundation and security

- [x] P0 BASE-001 Repair the invalid `AbstractUser` import, recreate the local virtual environment and establish a passing `manage.py check`/test baseline.
- [x] P0 SEC-001 Prevent public/self-service assignment of staff/admin roles.
- [x] P0 SEC-002 Add centralized capability/object-scope authorization to HTML, API, admin and jobs. Every routed API action and dynamic portal action has an automatically verified explicit valid role policy/default deny; every protected portal route has an authentication contract, admin uses centralized least privilege, and scheduled handlers are system-only.
- [x] P0 SEC-003 Scope users, guests, reservations, folios, payments, tasks and orders by role/property/ownership. Role and ownership scopes are enforced and tested across the approved V1 single-property boundary; a future multi-property model is explicitly outside V1 rather than an incomplete authorization control.
- [x] P0 SEC-004 Replace broad writable `ModelViewSet` behavior with explicit commands and allowed fields. Reservations, quotes, inventory blocks, housekeeping, maintenance, service orders/items, payments, cashier shifts, printing, folios and financial documents now use explicit commands or read-only resources; unsafe generic state/financial writes are denied.
- [x] P0 SEC-005 Add allow/deny permission matrix tests for every endpoint/action/export. Router-wide API policies, every protected portal route, all static/dynamic portal role policies, action-denial-before-object-lookup, ownership cases and CSV/PDF export boundaries are automatically verified; physical document rendering remains a separate QA/device launch gate.
- [x] P0 SEC-006 Add OTP expiry, hashed storage, attempt/resend limits and abuse monitoring.
- [x] P0 SEC-007 Replace emailed/displayed generated passwords with expiring setup links.
- [x] P0 SEC-008 Configure session/JWT lifecycle, token revocation if JWT retained, MFA-ready staff auth and secure cookies. Staff TOTP/recovery MFA is mandatory in production, secrets are encrypted, attempts/replay are controlled, JWT access is short-lived, refresh rotation/revocation is enabled, and production cookies are secure.
- [x] P0 AUD-001 Make audit coverage comprehensive and tamper-evident/append-only by policy. API commands, successful authenticated portal/admin mutations and scheduled jobs enter a serialized SHA-256 chain; model/queryset/bulk mutation and actor deletion are blocked, existing events are backfilled, and an integrity verifier is tested and documented.
- [x] P0 PLAT-001 Add production settings validation and remove insecure defaults outside development.
- [~] P0 PLAT-002 Adopt PostgreSQL and create rehearsed migration/rollback/reconciliation scripts. PostgreSQL runtime/configuration, automated invariant reconciliation and idempotent legacy-payment ledger backfill are implemented; signed live migration and restore rehearsal remain.
- [x] P1 PLAT-003 Add Redis, worker/scheduler and transactional outbox.
- [~] P1 PLAT-004 Add CI, checks, tests, dependency scanning and deploy gates. GitHub Actions now runs PostgreSQL/Redis migrations, migration drift, full tests, production deploy checks and pip-audit; branch protection must be enabled in repository settings.
- [x] P1 PLAT-005 Add feature flags and seeded configuration/permissions.

## Inventory, rates and reservations

- [~] P0 INV-001 Create transactional availability/allocation service with concurrent booking tests. Transactional room locking and shared overlap enforcement are implemented, and a real two-connection PostgreSQL contention contract is wired into CI; an accepted CI/staging execution record remains required.
- [x] P0 INV-002 Replace count-based human identifiers with collision-safe sequences/references.
- [x] P1 INV-003 Separate sellable inventory from physical room operational status.
- [x] P1 RATE-001 Add rate plans, daily prices, min/max stay, occupancy pricing and closed-to-arrival/departure rules. Adult/child per-night supplements are disclosed, taxed and snapshotted with the rate policy.
- [x] P1 RATE-002 Add effective-dated taxes, fees, service charges and rounding policy.
- [x] P1 RATE-003 Add promotions/packages/extras and approval-limited discounts. Usage-limited promotions, approval-limited discounts and room-type-aware, quantity-snapshotted bookable extras are complete.
- [x] P1 RES-001 Add quote/hold expiry and price/policy snapshots.
- [x] P1 RES-002 Add reservation source/channel, status history and assignment history.
- [x] P1 RES-003 Add amendments, extensions, room moves, no-shows, waitlist and cancellation fees.
- [x] P1 RES-004 Add corporate/group account support or explicitly defer through an ADR.
- [x] P1 GUEST-001 Add guest deduplication, companions, consent history and controlled identity data. Normalized duplicate detection, permission-controlled audited merges, companions, append-only consent and last-four-only identity capture are complete.

## Public website and guest experience

- [~] P1 WEB-001 Define brand system, content voice, approved photography and media pipeline. A reusable color/type/spacing system and evidence-based Abuja voice are applied; approved photography governance remains.
- [~] P1 WEB-002 Rebuild responsive public navigation/home/rooms/details/offers/services/contact/policies/FAQ. Shared responsive shell, homepage, room booking handoff, searchable FAQ and governed policy surfaces are complete; controlled policy drafts remain unpublished pending qualified review and owner approval.
- [x] P1 WEB-003 Add editable content, galleries, preview/publish, SEO metadata, sitemap and structured data. Room galleries now include ordered/featured media, draft publication controls, mandatory accessibility descriptions, admin editing, role-scoped API review, and published rendering across home/list/detail pages alongside the existing CMS preview, metadata, sitemap, robots and Hotel structured data.
- [x] P1 WEB-004 Build availability and booking funnel with full price/policy disclosure.
- [x] P1 WEB-005 Add analytics events for search, room view, checkout steps, errors and conversion.
- [x] P1 GPORT-001 Build guest stay, documents, payment, request and reservation-change views.
- [x] P2 WEB-006 Add local guide, reviews/testimonials workflow and multilingual readiness. Publish-gated guide places, locale variants (English/Hausa/French-ready), consented moderated testimonials, sitemap/search discovery and accessible public UI are implemented.

## Front desk, folios and POS

- [x] P1 FD-001 Build arrivals/in-house/departures/room-readiness today board.
- [x] P1 FD-002 Build calendar/tape chart, room rack and conflict-aware assignment.
- [x] P1 FD-003 Build walk-in/phone booking and keyboard-friendly check-in/out. The semantic today board now includes reservation/guest/phone/room search, labelled tables, skip/focus controls, responsive quick actions and verified `/`, `Alt+N` and `Alt+T` keyboard flows alongside explicit stay commands.
- [x] P0 FIN-001 Implement immutable folio ledger with charges, payments, refunds, reversals and adjustments. Accommodation, taxes, services, payments, refunds and manager-authorized compensating corrections post immutable entries.
- [x] P0 FIN-002 Add idempotent payment lifecycle and prohibit silent historical edits/deletes.
- [x] P1 FIN-003 Add invoices, receipts, credit notes, tax summaries and receivables based on ledger entries.
- [x] P1 POS-001 Add registered terminals, cashier shifts, floats, paid-in/out and expected cash.
- [x] P1 POS-002 Add close/variance approval and X/Z reports.
- [x] P1 POS-003 Add 80 mm/A4 print layouts, print profiles, retry and reprint audit. Print results, failure reasons, attempts, controlled retry, numbered reprints and completing actor are audited.
- [ ] P1 POS-004 Test agreed printer/browser/OS combinations at the hotel front desk.
- [ ] P2 PAY-001 Integrate selected online payment provider after PCI/scope decision.

## Operations

- [x] P1 HK-001 Build task assignment, mobile execution, inspection and turnaround SLA.
- [x] P1 HK-002 Add clean/inspected/dirty room-state reconciliation and discrepancy alerts. Inspection-gated release, maintenance conflicts, scheduled reconciliation, deduplicated alerts, routing and automatic clearance are implemented.
- [x] P1 MNT-001 Add maintenance tickets, downtime blocks, evidence, cost and return-to-service approval.
- [x] P1 SVC-001 Add outlet/service orders, preparation lifecycle and authorized folio posting.
- [x] P2 OPS-001 Add lost-and-found, incidents, linen/minibar/inventory. Controlled incident and lost-item registers provide role-scoped custody, claim, closure and disposal workflows; an append-only operational stock ledger now handles linen, minibar, housekeeping and maintenance supplies with non-negative balances, balanced transfers, idempotency, reorder visibility and departmental scope.

## Communications, inquiries and chat

- [x] P1 COM-001 Add communication template/version, message, recipient, consent and delivery-event models.
- [x] P1 COM-002 Add Brevo transactional adapter with retry/idempotency and provider IDs.
- [x] P1 COM-003 Add authenticated webhook ingestion for delivered/bounced/deferred/open/click/complaint/unsubscribe events.
- [x] P1 COM-004 Add Brevo contact sync, newsletter preferences, suppression and unsubscribe reconciliation. Database-scheduled Brevo v3 contact upserts preserve local suppression precedence, retry failures and expose per-contact health.
- [x] P1 CRM-001 Add inquiry/case inbox, categories, routing, SLA, ownership, notes and attachments. Evidence files are constrained, immutable and served through permission-checked downloads; configurable category/source routing controls owner, priority and SLA.
- [x] P1 CHAT-001 Add conversation/message/participant/assignment models and WebSocket transport.
- [x] P1 CHAT-002 Add visitor widget, agent console, business hours, queue, offline capture and transcript. Outside configured hours, email-identified conversations become linked inquiry cases with an acknowledgement and durable transcript.
- [x] P2 CHAT-003 Add approved canned replies, typing/presence and satisfaction feedback. Server-validated approved replies, usage tracking, ephemeral peer presence/typing, and one-time sanitized post-close feedback are implemented and tested.

## Management and reporting

- [x] P1 RPT-001 Approve metric catalog with business date, formula and drill-down source.
- [x] P1 RPT-002 Build reliable revenue/occupancy/ADR/RevPAR/pace/source/receivable dashboards.
- [x] P1 RPT-003 Add operational SLA, room discrepancy, cashier variance and communication exception dashboards.
- [x] P1 RPT-004 Add night audit and reproducible daily manager pack.
- [x] P1 RPT-005 Add scheduled, permission-scoped, expiring PDF/CSV exports.
- [x] P1 MGMT-001 Add management query cases linked to source records, SLA, evidence and resolution history.
- [x] P2 AUTO-001 Add configurable alerts/escalations with retries, failure queue and audit. Enumerated configurable domain rules, deduplicated lifecycle alerts, role routing, acknowledgement/resolution history, scheduled retries, stale-lock recovery, auto-pause and management visibility are implemented.

## Quality, privacy and operations

- [x] P0 QA-001 Add domain/unit tests for inventory, pricing, transitions, ledger and authorization. Inventory, pricing, reservation/operations transitions, financial and stock ledgers, router-wide API authorization, portal-route/action policies and cross-role ownership invariants are covered by the automated suite.
- [x] P1 QA-002 Add end-to-end journeys for booking, check-in, settlement, receipt, checkout and shift close.
- [x] P1 QA-003 Add contract/integration tests for Brevo, webhooks, payments and print documents. Coverage includes mocked Brevo email/contact contracts, authenticated webhooks, payment idempotency, A4 line totals, 58/80 mm thermal CSS, long content, ownership, reprint and failure/retry lifecycle.
- [~] P1 QA-004 Automated semantic/mobile markup, critical-page accessibility, duplicate-ID, image-alt, form-label, query-budget, HTML-size and print-contract tests are implemented; physical cross-browser/mobile and printer certification remains a launch gate.
- [~] P1 OPS-002 Add structured logs, error tracking, metrics, traces, alerts and operational dashboards. Correlated redacted JSON request logs now carry request/trace/span/release identity, and vendor-neutral OTLP auto-instrumentation covers Django/ASGI, PostgreSQL, Redis and outbound HTTP alongside readiness, worker/job health and exception dashboards; collector dashboards, routing and alert delivery remain deployment activation gates.
- [~] P0 OPS-003 Add encrypted backups, retention, restore drills and documented RPO/RTO. AES-256-GCM PostgreSQL backup creation, checksum/archive verification, proposed RPO/RTO, retention and isolated restore procedure are implemented; managed PITR/storage scheduling and a signed live restore rehearsal remain external deployment gates.
- [~] P1 PRIV-001 Access/export, correction, anonymization, suppression, expiry and legal-hold controls are implemented and tested; qualified Nigerian privacy/fiscal review and owner approval remain launch gates.
- [x] P1 DOC-001 Create operator, admin, management, incident, backup and deployment runbooks.
- [ ] P1 LAUNCH-001 Complete migration rehearsals, training, UAT, security test and rollback drill.

## Universal definition of done

Every backlog item must include acceptance criteria, policy checks, audit behavior, migrations/backfill if relevant, automated tests, loading/error/empty UI states, accessibility review, telemetry, documentation and rollback/feature-flag consideration. Acceptance requires product owner and operational owner sign-off for workflow changes.
