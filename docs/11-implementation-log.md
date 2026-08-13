# Implementation Log

This log records accepted delivery increments after the verified baseline. The master backlog remains the status source of truth.

## Tamper-evident unified audit chain

- Added a locked singleton chain head, monotonic unique sequence, previous-event hash and canonical SHA-256 event hash to the unified audit log.
- Backfilled existing audit events deterministically and changed audit actors to protected references so later account deletion cannot silently alter signed payloads.
- Blocked instance updates/deletes, queryset updates/deletes and bulk creation. Audit events must pass through serialized individual appends.
- Added payload-free middleware coverage for every successful authenticated non-API write and unified scheduled-job execution events; existing API action records remain richer and non-duplicated.
- Added `manage.py verify_audit_chain` plus tests for linked appends, model immutability, actor protection, raw SQL tamper detection, chain-head consistency, request privacy and worker coverage.

## API policy and command hardening

- Added a router-wide policy contract test that enumerates every registered API action, requires an explicit valid role mapping and verifies default denial plus the allow/deny result for every hotel role.
- Converted invoices, invoice items and receipts to read-only API resources so generic writes cannot bypass folio/payment services.
- Replaced generic service-order-item mutations with ownership-scoped add/remove commands that lock the order, enforce pending state, availability and quantity limits, and retain server-authoritative prices.
- Converted notifications to a read-only resource with explicit mark-read commands and removed internal room notes from guest API representations while preserving staff visibility.
- Expanded cross-role regression coverage for financial mutations, service-order ownership/state boundaries and sensitive representation fields.

## Operational alerts and domain escalation

- Added configurable alert rules for room-state discrepancies, overdue housekeeping, overdue maintenance, unanswered chat, inquiry SLA breaches and scheduled-job failures.
- Seeded safe production defaults and a five-minute database-backed evaluator job using the existing claim/retry/stale-lock/auto-pause scheduler.
- Alerts use stable deduplication keys, occurrence counts, severity, source links, role-based in-app routing and immutable lifecycle history. Cleared conditions resolve automatically; recurring conditions reopen and notify again.
- Added management control-center actions for acknowledgement and evidence-backed resolution, plus read-only administration and rule configuration.
- Added tests for every rule type, deduplication, notification suppression on repeat detection, management controls, scheduler execution, history immutability and automatic resolution.

## Live-chat operator assistance

- Added draft/approved/retired canned replies with controlled administration, recorded approver/time, categories and usage counts.
- The staff reply workflow resolves canned content on the server and rejects draft/retired identifiers, preventing browser-side substitution of unapproved wording.
- Added WebSocket presence and throttled typing signals to the guest widget and agent conversation view. Signals are derived from the authenticated participant, shared only with peers, and are never stored in chat transcripts.
- Added focused workflow and two-peer WebSocket tests for approval enforcement, usage accounting, presence, typing and non-persistence.

## Local discovery, reviews and multilingual readiness

- Added a publish-gated local guide with categories, journey estimates, map/website links, optional imagery, ordering and English fallback content.
- Added publish-gated Hausa/French-ready translations for CMS page metadata/heroes and local-guide content, with a persistent public language selector.
- Added consent-required guest testimonial submission, pending moderation by default, and controlled admin approval/rejection. Only approved consented testimonials render publicly.
- Added the guide to primary navigation, public search and sitemap discovery.
- Added automated semantic/mobile checks for critical public pages, image alternatives, unique IDs, form labels, headings, language metadata, query limits and document-size limits; the gate identified and fixed missing headings and live-chat labels.

## Privacy governance workflow

- Added guest self-service requests for data access/export, correction, and anonymization, plus an admin/management review and execution queue.
- Added protected seven-day JSON exports, owner/management download authorization, immutable workflow history, duplicate-request controls, and legal-hold/active-stay/open-balance anonymization blockers.
- Anonymization removes operational profile and communication identifiers while preserving financial/stay records and a minimum suppression marker needed to prevent future marketing contact.
- Added automated coverage for authorization, export contents and expiry, legal holds, suppression, anonymization, duplicate requests, and immutable history.
- Legal interpretation, the final retention schedule, and policy wording remain subject to qualified review and owner approval before launch.

## 2026-08-09 — Phase 1 authorization slice 1

### Delivered

- Added a centralized, default-deny DRF action-role permission class.
- Removed anonymous access to the general user-create endpoint while retaining explicit login and guest registration endpoints.
- Prevented public registration and profile self-update from assigning privileged roles.
- Restricted user and guest-directory APIs to approved staff roles.
- Applied action-level roles to room catalog, reservations, billing, payments, services, housekeeping and notifications.
- Scoped guests to their own reservations, invoices, invoice items, receipts, payments, service orders/items and notifications.
- Scoped housekeeping users to tasks assigned to them.
- Made guest reservation and service-order ownership server-controlled.
- Made reservation/service-order statuses server-controlled during generic creation/update paths.
- Disabled arbitrary notification creation through the user-facing API.

### Verification

- `pip check`: passed.
- `manage.py check`: passed with no issues.
- `makemigrations --check --dry-run`: no changes detected.
- Full test suite: 24 tests passed in 102.039 seconds.

### Remaining authorization work

- Replace role sets with seeded capabilities, property/department assignments and approval thresholds.
- Move state changes from generic model updates into audited command services.
- Apply the same policy layer to all HTML views, Django admin actions, exports and background jobs.
- Complete an endpoint-by-endpoint allow/deny matrix, including field-level and object-level cases for every role.
- Add audit events for API mutations and denied high-risk operations.

## 2026-08-09 — Phase 1 authorization slice 2

### Delivered

- Scoped dashboard reservation, revenue, balance, service and housekeeping metrics by role.
- Prevented guest room-detail pages from exposing other guests' reservation history.
- Blocked housekeeping accounts from billing, payment, service-order and room-reservation portals.
- Made the management staff directory read-only for managers; staff creation and account actions now require an administrator.
- Added audit records for administrator staff account actions.
- Updated portal role decorators to recognize Django superusers consistently.
- Removed unavailable staff-management controls from the manager UI.

### Verification

- Dependency, Django system and migration checks passed.
- Full test suite: 27 tests passed in 115.294 seconds.

### Next slice

- Secure authentication and OTP lifecycle, API mutation auditing, and Django-admin policy enforcement.

## 2026-08-09 — Phase 1 authentication and audit slice

### Delivered

- Replaced plaintext booking OTP session storage with Django password hashes.
- Added configurable 10-minute OTP expiry, attempt lockout, email/IP send throttling and session-key rotation.
- Clear verification state on expiry, lockout, successful use or email-delivery failure.
- Changed HTML email delivery to return a reliable result and log exceptions instead of printing/suppressing failure.
- Fixed the verified-booking date conversion defect that crashed valid OTP completion.
- Added a reusable API mutation audit mixin across all domain viewsets.
- Added centralized Django-admin permissions: administrators may mutate, managers are read-only, other roles are hidden.
- Made audit records immutable through Django admin.
- Updated the verification email to match the configured ten-minute expiry.

### Verification

- Dependency, Django system and migration checks passed.
- Full test suite: 32 tests passed in 210.583 seconds.

### Next slice

- Replace generated/emailed guest passwords with single-use password setup links, add login throttling/security events, and begin command-service/state-machine extraction.

## 2026-08-09 — Phase 1 secure onboarding slice

### Delivered

- Replaced booking-created guest passwords with unusable-password accounts and 24-hour, single-use Django setup tokens.
- Added a password-setup route and responsive portal page; successful setup signs the user in and invalidates token replay.
- Reworked booking confirmation email to contain a setup link and username but no password.
- Replaced administrator-created temporary staff passwords with emailed single-use staff invitations.
- Added shared account/IP login throttling for portal and API authentication.
- Added authentication audit events for successful, failed and blocked portal/API attempts.
- Added configurable setup-token and login-throttle settings to environment documentation.

### Verification

- Dependency, Django system and migration checks passed.
- Full test suite: 34 tests passed in 163.556 seconds.

### Next slice

- Extract reservation lifecycle commands, enforce transactional availability across HTML/API booking paths, and replace collision-prone identifiers.

## 2026-08-09 — Reservation integrity slice

### Delivered

- Added a shared transactional reservation command service used by authenticated public booking, verified-email booking, staff portal booking, room-detail booking and REST API creation.
- Added room row locking plus consistent pending/confirmed/checked-in overlap protection.
- Centralized date, active room, maintenance/out-of-order and maximum-occupancy validation.
- Added a guarded reservation state machine for confirmation, check-in, checkout, cancellation and no-show.
- Unified confirmation invoice/notification and checkout housekeeping side effects across portal and API paths.
- Disabled generic API update/delete so state changes cannot bypass commands.
- Updated the availability API so pending allocations block room results.
- Replaced count-based reservation, invoice, receipt and service-order identifiers with collision-resistant year-prefixed references.

### Verification

- Added command tests for overlap, adjacent stays, dates, occupancy, room state, transitions, invoices, room status, housekeeping and references.
- Dependency, Django system and migration checks passed.
- Full test suite: 39 tests passed in 181.955 seconds.

### Remaining boundary

- SQLite cannot prove real row-lock concurrency. The PostgreSQL migration and multi-connection contention test remain required before claiming production-safe allocation.

### Next slice

- Introduce production settings and PostgreSQL configuration, add database-backed status history and reservation source snapshots, then verify real concurrent allocation behavior.

## 2026-08-09 — Production data and reservation history slice

### Delivered

- Added PostgreSQL `DATABASE_URL` parsing, persistent connection health checks and psycopg runtime dependency.
- Added a hardened production settings module that refuses weak secrets, empty hosts and non-PostgreSQL databases.
- Enabled secure cookies, HTTPS redirect, HSTS, trusted-origin configuration and SMTP email in production.
- Set configurable hotel currency and Africa/Lagos property timezone defaults.
- Added reservation source, channel reference, price snapshot and policy snapshot fields.
- Added append-only reservation status history and room-assignment history models.
- Shared commands now record creation/transition actors, source, price basis, status changes, initial assignment and checkout release.
- Added read-only history to reservation APIs and Django admin.
- Added a data migration that backfills existing reservations and preserves historical timestamps.

### Verification

- Production `check --deploy` passed against a syntactically valid PostgreSQL configuration.
- Migration consistency and migration plan passed.
- Dependency integrity and Django system checks passed.
- Full test suite: 39 tests passed in 196.230 seconds.

### Remaining boundary

- A running PostgreSQL service and production-like dataset are still required for live migration reconciliation, rollback/restore rehearsal and multi-connection contention proof.

### Next slice

- Build rate plans, effective-dated room pricing, taxes/fees and policy snapshots, then introduce expiring inventory holds and quote commands.

## 2026-08-09 — Rates, quotes and inventory holds slice

### Delivered

- Added room-type rate plans with inclusions, refundability, deposit, cancellation policy and min/max stay rules.
- Added effective-dated nightly overrides, minimum stay and closed-to-arrival/departure controls.
- Added effective-dated percentage and fixed-per-stay taxes/fees with explicit half-up currency rounding.
- Added authoritative price calculation with nightly breakdown, subtotal, taxes, total and required deposit.
- Added immutable booking quotes and expiring room inventory holds.
- Added transactional quote conversion that preserves exact price/policy snapshots and can execute only once.
- Active holds now block direct reservation commands, competing quotes and availability API results.
- Added hold expiry/release commands and automatic standard rate plans for new/existing room types.
- Integrated ten-minute quote/hold creation into public booking before OTP delivery; verification converts the exact quote.
- Added role-scoped quote creation/conversion APIs and read-only quote/rate administration.
- Updated confirmation invoices to use snapped accommodation and tax amounts without re-taxing them.

### Verification

- Added tests for daily overrides, percentage/fixed taxes, deposits, hold conflicts, expiry, one-time conversion, API ownership and public OTP conversion.
- Dependency, Django system and migration consistency checks passed.
- Full test suite: 43 tests passed in 166.827 seconds.

### Next slice

- Build the hotel folio/ledger, idempotent tenders/refunds and cashier terminal/shift model that will underpin front-desk POS and thermal receipts.

## 2026-08-09 — Folio, cashiering and thermal receipt slice

### Delivered

- Added reservation folios and append-only debit/credit entries with unique external keys.
- Confirmation now posts snapped accommodation and tax charges exactly once.
- Added idempotent payment and refund commands with compensating folio entries and invoice reconciliation.
- Prevented financial ledger, refund and cash movement edits/deletes by model policy and admin/API configuration.
- Added registered 58/80 mm cashier terminals, one-open-shift constraints, opening floats, cash sale/refund movements and expected-cash reconciliation.
- Added cashier close variance controls; variances above the configured threshold require an authenticated admin/manager to perform approval.
- Added a front-desk cashier page for opening and closing shifts.
- Added payment-linked receipts, dedicated thermal print layout, numbered reprint jobs and portal/API print requests.
- Added role/ownership-scoped read-only folio and folio-entry APIs.

### Verification

- Added financial invariant tests for payment/refund idempotency, immutable ledgers, cash variance approval and reprint numbering.
- Payment tests: 5 passed; frontend workflow tests: 24 passed.
- Django system and migration consistency checks passed.

### Remaining boundary

- Paid-in/out commands, X/Z report documents, credit notes, printer worker retries and physical printer/browser testing remain.

### Next slice

- Complete front-desk today board and stay commands, then add X/Z reporting and controlled financial adjustments.

## 2026-08-09 — Front desk and service delivery slice

### Delivered

- Added a role-scoped front-desk today board for arrivals, in-house guests, departures, overdue pending reservations and live room readiness.
- Added manager-authorized, idempotent paid-in/paid-out cashier movements.
- Added reproducible X reports for open shifts and Z reports for closed shifts through the cashier API.
- Replaced generic service-order API mutations with explicit lifecycle commands.
- Completing a priced service order now posts an idempotent charge to the linked reservation folio.

### Verification

- Added front-desk role/scope coverage and paid-in/X/Z financial tests.
- Focused front-desk, service lifecycle and payment suites passed.

### Next slice

- Harden housekeeping assignment/inspection and room-state reconciliation, then build maintenance downtime tickets.

## 2026-08-10 — Housekeeping inspection and maintenance slice

### Delivered

- Centralized housekeeping create/start/complete/verify/reopen commands across portal and API.
- Added assignment enforcement, completion notes, supervisor inspection notes and verified-by/timestamp evidence.
- Rooms remain in housekeeping until an authorized supervisor verifies readiness.
- Added append-only housekeeping transition history.
- Added maintenance tickets with room/category/priority, owner, evidence, estimated/actual costs and downtime control.
- Urgent downtime moves rooms out of order; other downtime moves rooms into maintenance.
- Added report/start/resolve/approve/reopen/cancel commands with immutable history.
- Return to service requires admin/manager approval and automatically creates a high-priority inspection task.
- Open downtime prevents housekeeping from releasing a room as available.
- Added role-scoped maintenance portal, API endpoints and management administration.

### Verification

- Added tests for inspection-gated release, assignment and supervisor controls, downtime conflicts, management approval, immutable histories and portal authorization.
- Focused operations and affected portal suites passed.

### Next slice

- Add communication outbox/template/delivery models and the Brevo transactional adapter with signed webhook reconciliation.

## 2026-08-10 — Brevo outbox, newsletter consent and inquiry slice

### Delivered

- Added versioned communication templates, immutable send intent identifiers, outbound messages, attempts and delivery events.
- Added a provider-neutral email outbox with immediate development delivery and scheduler-friendly queued/retry processing.
- Added a Brevo adapter using the transactional email endpoint, provider message IDs, request idempotency, sandbox mode and transient backoff.
- Added authenticated, idempotent Brevo webhook ingestion for delivery, engagement, deferral, bounce, block, complaint and unsubscribe events.
- Added local contact preferences and suppression precedence; complaints/hard bounces/invalid addresses prevent further sends.
- Routed all existing branded application email through the logged outbox.
- Added consent-aware newsletter subscription, suppression-aware approved campaign dispatch and per-campaign recipient counts.
- Converted the public contact form into inquiry cases with categories, priority-based response/resolution SLA, ownership, status history and acknowledgement email.
- Added staff inquiry inbox/detail workflows, public replies, internal notes and audited lifecycle commands.

### Verification

- Tested application delivery logging/idempotency, marketing suppression, Brevo provider IDs, webhook authentication/duplicates/unsubscribe reconciliation, newsletter filtering and inquiry ownership/SLA/replies.
- Official implementation contract verified against Brevo's transactional email and secured webhook documentation on 2026-08-10.

### Remaining boundary

- Brevo Contacts API synchronization, inquiry attachments/configurable routing, Redis-backed workers and live chat remain.

### Next slice

- Add authenticated live-chat conversations/messages, visitor widget, queue assignment and agent console with Redis-backed Channels transport.

## 2026-08-10 — Live chat slice

### Delivered

- Added durable visitor/guest conversations, queue, assignment, messages, internal notes, status history, disposition and reservation/inquiry links.
- Added visitor-token and authenticated guest/staff authorization at every conversation boundary.
- Added duplicate-safe client message IDs, message length limits, sanitization and per-sender throttling.
- Added Channels WebSocket transport protected by allowed-origin and session authentication middleware.
- Added Redis channel-layer configuration for production and an in-memory development/test layer.
- Added a responsive public visitor widget with WebSocket delivery and HTTP polling/send fallback.
- Added staff queue/filter console, transcript view, assign/wait/reopen/close commands, replies and internal notes.
- Added Daphne ASGI runtime dependencies and production requirements for Redis and Brevo secrets.

### Verification

- Tested visitor token isolation, HTML sanitization, idempotent messages, assignment/reply/close lifecycle, polling access scope and real ASGI WebSocket connect/send/reject behavior.
- ASGI application import and Django system checks passed.

### Remaining boundary

- Business hours/offline conversion, file attachments, canned replies, presence/typing and satisfaction feedback remain.

### Next slice

- Build the management metric catalog, reconciled revenue/occupancy/ADR/RevPAR dashboards, night audit and management query cases.

## 2026-08-10 — Management intelligence and night audit slice

### Delivered

- Added a seeded metric catalog with approved formulas, units and source models for occupancy, ADR, RevPAR, total revenue, receivables and cashier variance.
- Added live management metrics reconciled from reservation, folio, cashier, housekeeping and service records.
- Added immutable daily metric snapshots with source hashes, reservation-source breakdown and operational SLA values.
- Added controlled night audit that rejects future/current dates, duplicate closes, open cashier shifts and unresolved arrivals/departures.
- Added management dashboard with live KPIs, night-audit close history and drillable management query inbox.
- Added management query cases with source links, priority-based SLA, assignment, investigation, evidence/notes, resolution and immutable status history.

### Verification

- Tested exact occupancy/revenue/ADR/RevPAR/receivable reconciliation against ledger sources.
- Tested one-time immutable night audit and query assignment/investigation/resolution history.
- Tested management portal role isolation and query creation.

### Remaining boundary

- Booking pace, consolidated exception drill-down and scheduled PDF manager packs remain.

### Next slice

- Complete reservation amendments/room moves/no-shows, guest profiles/companions and front-desk tape chart, then harden public and guest experiences.

## 2026-08-10 — Front-desk stay management slice

### Delivered

- Added explicit audited stay amendment/extension commands with inventory revalidation and repricing.
- Positive amendments post immutable folio adjustments; reductions post compensating credit notes.
- Added conflict-aware room moves with assignment release/history, occupied-room state transfer and automatic cleanup task for the vacated room.
- Added a fourteen-day room tape chart with status-coded occupied cells and direct reservation drill-down.
- Added staff stay-management workspace for amendments, room moves, companions and consent history.
- Added companion records with controlled last-four-only identity capture and append-only guest consent records.
- Added staff no-show action to the reservation portal.
- Added prioritized waitlist records with expiring offers and one-time conversion through the authoritative inventory command.
- Added amendment/companion history to APIs and waitlist command endpoints.

### Verification

- Tested extension pricing and folio adjustment, checked-in room move state/history/cleanup, waitlist one-time conversion and tape-chart role scope.

### Remaining boundary

- Configurable cancellation fees, guest deduplication/merge and final keyboard/accessibility optimization remain.

### Next slice

- Build the guest self-service stay/document/request experience and begin the responsive public-site design/SEO/accessibility overhaul.

## 2026-08-10 — Guest self-service and public experience slice

### Delivered

- Added an ownership-scoped My Stay workspace for guest reservations, invoices, folios, payments and linked service/change inquiries.
- Added a reusable public design layer with responsive spacing, accessible focus states, reduced-motion support and mobile chat constraints.
- Rewrote the homepage proposition around the real Abuja property and disclosed the authoritative ten-minute quote hold before guest data submission.
- Connected room-detail date and occupancy selection to the existing transactional quote/hold funnel with the selected room preserved.
- Removed unsupported legacy reviews, ratings, social links and policy placeholders rather than presenting unverifiable claims or dead controls.
- Added canonical and social metadata, Hotel JSON-LD, public-only sitemap and robots controls that exclude the staff portal.
- Added publish-gated editable page metadata and hero content in Django admin, with authenticated staff preview through `?preview=1`.

### Verification

- Rendered and inspected the homepage at desktop and 390 px mobile widths, plus the rooms catalog and room-detail booking handoff.
- Browser console remained clear of warnings/errors during the inspected journeys.
- Added focused tests for crawl metadata, editable published content, sitemap boundaries and room-detail booking inputs.

### Remaining boundary

- Photography approval, galleries, owner-approved legal/policy/FAQ copy, analytics provider selection and formal cross-browser/device testing require business or hardware decisions.

## 2026-08-10 — Commercial configuration and quote-conversion slice

### Delivered

- Added seeded runtime feature flags for public booking, live chat and future online payments, plus editable operational settings for business hours, manager packs and role discount limits.
- Added date-, room-type-, minimum-stay- and usage-constrained promotions with transactional usage enforcement and immutable quote snapshots.
- Added configurable refundable/non-refundable cancellation policy snapshots and compensating folio reversals plus cancellation-fee entries.
- Added corporate credit accounts, payment terms, group room targets and explicit reservation links through admin, API and the staff commercial portal.
- Added separation-of-duty reservation discount requests: reception can request, managers/admins approve within configured limits, and approval posts an immutable credit note.
- Added a pre-verification quote review page showing each night, promotion discount, taxes, total, deposit and cancellation terms under the active inventory hold.
- Added privacy-limited first-party events for search, room views, quote creation/view/confirmation/cancellation, booking errors and conversion.
- Corrected the dated-room availability API to use the actual reservation date fields.

### Verification

- Focused commercial tests cover promotion snapshots and one-time usage, cancellation ledger reconciliation, corporate/group API linkage, discount approval controls and portal role scope.
- Focused public tests cover the itemized quote boundary and booking feature shutdown.
- Rendered the itemized quote on desktop and 390 px mobile layouts; no browser console warnings/errors were observed.

## 2026-08-10 — Reporting automation and worker-control slice

### Delivered

- Added source-driven seven-day booking pace against the prior comparable window for the next 30 arrival days.
- Added one management exception catalog covering overdue housekeeping, room discrepancies, maintenance approvals, cashier variances, delivery failures/deferrals, inquiry SLA breaches and chat queue waits.
- Added immutable daily manager packs containing reconciled metrics, booking pace and exception values in PDF and CSV.
- Added manager-only, expiry-enforced pack downloads and manual/scheduled generation with idempotency by business date.
- Added database-backed scheduled jobs for the email outbox, inventory-hold expiry and daily manager packs.
- Added atomic claiming, stale-lock recovery, retry cadence, consecutive-failure tracking, automatic pause and immutable job executions.
- Added worker/scheduler health and recent failure visibility to the management portal.
- Repaired the inquiry-detail portal fall-through and added regression coverage.
- Hardened direct reservation model creation so string decimal inputs cannot concatenate when calculating stay totals.

### Verification

- Reporting tests cover ledger metrics, booking pace, exception sources, immutable/permission-scoped manager packs and inquiry detail rendering.
- Worker tests cover successful claim/reschedule and visible auto-paused failure state.
# 2026-08-10 - Sellable inventory, extras and guest identity

- Separated physical room operational state from future sellability with a permanent room switch and effective-date inventory blocks.
- Linked maintenance downtime to controlled sales blocks and approved return-to-service release.
- Added room-type-aware bookable extras with per-stay, per-night and per-guest/night quantities, tax treatment, quote snapshots and folio posting.
- Added admin, API and management portal surfaces for inventory blocks and extras.
- Replaced full identity-number storage with a data-preserving last-four-only migration.
- Added normalized guest email/phone indexes, duplicate review, role-controlled merge commands and immutable merge history.
- Merge transfers linked reservations, quotes, waitlist entries, financial records, service orders, notifications, inquiries, chat and consent history while preserving an audit snapshot.
- Added focused clean-database migration and behavior coverage for inventory, extras and guest identity.

## 2026-08-10 - Controlled financial corrections

- Added manager/admin-only debit-adjustment and credit-note commands over open folios.
- Every correction creates both an immutable compensating folio entry and an immutable authorization record containing requester, authorizer and reason.
- Added role-scoped API actions, successful-mutation audit events and a management billing-portal workflow.
- Added date-filterable tax summaries derived directly from immutable tax ledger entries.
- Added migration `billing.0003_financialcorrection` and focused invariant, authorization, API and portal tests.

## 2026-08-10 - Inquiry routing, protected evidence and chat hours

- Added ordered inquiry routing rules that match category/source and configure owner, priority, first-response SLA and resolution SLA.
- Added immutable PDF/JPEG/PNG/text inquiry evidence with a 5 MB limit and authorization-checked downloads.
- Added configurable weekday live-chat hours; outside hours an email is required and the transcript becomes a linked inquiry case automatically.
- Added one-time, sanitized 1–5 satisfaction feedback after chat closure and surfaced offline/feedback state in the agent console.
- Added migrations `notifications.0006` and `notifications.0007` plus routing, file authorization, offline conversion and feedback tests.

## 2026-08-10 - Occupancy pricing

- Added configurable included-adult counts plus extra-adult and child per-night supplements to rate plans.
- Occupancy supplements are itemized in quote review, included in promotion calculations and taxable base, and snapshotted with price and policy evidence.
- Added migration `rooms.0005_rateplan_child_per_night_and_more` and focused pricing coverage.

## 2026-08-10 - Brevo Contacts synchronization

- Implemented Brevo v3 contact upserts with `updateEnabled`, explicit email blacklist state and optional marketing-list assignment.
- Local inactive subscriptions, withdrawn preferences and suppression records always override marketing consent.
- Added per-contact status, provider ID, retry/backoff and error evidence plus a seeded database scheduler job and management exception view.
- Added `BREVO_CONTACT_LIST_ID`, migration `notifications.0008`, and mocked provider-contract tests for consent and unsubscribe synchronization.

## 2026-08-10 - Cross-domain stay journey

- Added an end-to-end walk-in journey spanning quote hold, reservation conversion, confirmation/invoice/folio, POS shift, cash settlement, receipt print job, check-in, checkout, housekeeping creation and balanced Z close.
- Added a failure-path journey proving cash settlement requires an open shift and identical idempotency keys cannot double-charge or duplicate receipts.

## 2026-08-10 - Encrypted backup controls and runbooks

- Added PostgreSQL custom-dump backup creation encrypted with AES-256-GCM and a scrypt-derived key.
- Added adjacent SHA-256 manifests and verification of checksum, authenticated decryption and `pg_restore --list` readability without database mutation.
- Commands refuse SQLite, weak/missing keys, empty dumps, tampered archives and failed PostgreSQL utilities, while deleting plaintext temporary files.
- Added operator, admin, management, incident, backup/restore and deployment/rollback runbooks with ownership and evidence gates.
- Added command/cryptographic safety tests and pinned the direct `cryptography` dependency.

## 2026-08-10 - Operational health and structured logging

- Added validated/generated request IDs propagated as `X-Request-ID` and across context-aware JSON logs.
- Logs include method, path without query/body, status, duration and authenticated actor ID while excluding secrets and request payloads.
- Added unauthenticated liveness and readiness probes; readiness validates database, cache and overdue scheduler jobs and returns 503 with component state.
- Added structured-format, correlation, ready and stale-scheduler tests.

## 2026-08-10 - Print document contracts and lifecycle

- Added controlled printed/failed/retry commands with failure reason, attempt count, timestamps and completing actor.
- Fixed non-cash receipt rendering to derive its configured terminal from the print job.
- Added deterministic 58/80 mm thermal layout, long-name, reprint, guest ownership and A4 line-total contracts.
- Corrected the A4 template to use the actual invoice-item total and stable `NGN` currency text.
- Added migration `payments.0003` and a physical printer certification checklist.
## 2026-08-10 - Staff MFA and revocable API sessions

- Added encrypted TOTP staff devices, hashed one-use recovery codes, replay protection, bounded clock tolerance, failed-attempt lockout, controlled administrator reset and tamper-evident security events.
- Added pre-authentication portal enrollment/challenge flows, an authenticated MFA status surface, mandatory production enforcement, and equivalent enforcement for staff API login while leaving guest login unchanged.
- Reduced JWT access lifetime to 15 minutes, enabled refresh rotation/blacklisting, made logout require and revoke a valid refresh token, and exposed the standard refresh endpoint.
- Added production key validation, operational recovery/key-rotation guidance, and eight focused security tests.
- Accepted baseline: migration drift clean, dependency check clean, production deploy check clean, local audit chain verified, and all 156 tests passed in 363.896 seconds.

## 2026-08-10 - Managed room galleries

- Added ordered room-type gallery media with a single featured image, captions, mandatory accessibility descriptions, explicit draft/published state and admin inline management.
- Replaced fixed public placeholders with published gallery media on the homepage, room listing and room detail surfaces while retaining safe configured/static fallbacks.
- Kept unpublished media out of guest API and HTML responses while allowing managers and administrators to review drafts through the catalog API/admin boundary.
- Added migration `rooms.0006` and four gallery contracts covering public draft isolation, accessible rendering, role visibility and database-enforced featured-image uniqueness.
- Accepted baseline: migration drift clean, focused gallery/quality suite passed, and all 160 tests passed in 374.908 seconds.

## 2026-08-10 - Incident and lost-and-found registers

- Added controlled incident reporting, assignment, investigation, management resolution/closure and immutable lifecycle evidence linked to rooms and reservations.
- Added lost-item registration, secure custody, verified claim, return and management-only disposal lifecycles with claimant PII hidden from housekeeping users.
- Added a role-scoped operational portal, controlled admin review, tamper-evident audit events, migration `housekeeping.0003`, and three domain/authorization contracts.
- Accepted baseline: migration drift clean, focused operational contracts passed, and all 163 tests passed in 388.523 seconds.

## 2026-08-10 - Operational stock ledger

- Added locations, categorized stock items, materialized non-negative balances and immutable receipt/issue/waste/adjustment/transfer movements for linen, minibar, housekeeping and maintenance supplies.
- Added atomic balanced transfers, stable lock ordering, strict quantity validation, replay-safe UUID idempotency with payload mismatch rejection, reorder highlighting and role/category scope.
- Added an operational stock portal, controlled configuration/read-only ledger admin, migration `housekeeping.0004`, operator procedures and four balance/authorization/idempotency contracts.
- Accepted baseline: migration drift clean, focused stock contracts passed, and all 167 tests passed in 385.232 seconds.

## 2026-08-10 - Keyboard-first front desk

- Rebuilt the today board with real reservation/guest/phone/room search, one semantic page heading, labelled search, accessible arrival/departure tables, focus target and a portal-wide skip link.
- Added `/` search focus plus `Alt+N` new-reservation and `Alt+T` tape-chart shortcuts, removed the non-functional global search control, and connected the reservation fragment to a focusable creation surface.
- Verified the live portal in the in-app browser at desktop and 390 px mobile widths: zero horizontal overflow, shortcut focus/navigation passed, semantic controls were visible and no console warnings/errors occurred.
- Accepted baseline: focused front-desk/public quality contracts passed, migration drift remained clean, and all 168 tests passed in 388.575 seconds.

## 2026-08-10 - Route-wide portal authorization contracts

- Added machine-readable metadata to static role and dynamic action decorators and converted staff/newsletter mutation routes from coarse page roles to explicit per-action allowlists.
- Added a URL-enumerating contract that fails when any protected portal route lacks authentication, any dynamic action lacks a valid policy, or any static/dynamic role policy permits a known-denied role before object lookup.
- Added explicit guest/housekeeping denial and manager content-type/disposition contracts for CSV and PDF report exports.
- Accepted the single-property V1 authorization boundary defined in product requirements and completed SEC-002, SEC-003, SEC-005 and QA-001; multi-property tenancy remains a separately scoped future product capability.
- Accepted baseline: five portal policy/export contracts passed, migration drift remained clean, and all 173 tests passed in 409.382 seconds.

## 2026-08-10 - Governed policies and FAQ

- Added searchable, responsive FAQ and guest-policy indexes, published policy detail pages, navigation/footer discovery, sitemap entries and safe FAQPage structured data.
- Added controlled policy drafting, effective dates, versioned approval fingerprints, admin-only approval/publication/withdrawal actions and tamper-evident audit events. Any substantive edit automatically withdraws publication and invalidates approval.
- Seeded six factual operational FAQs and six clearly marked policy drafts that remain unpublished until qualified review and owner approval.
- Prevented internal room notes and draft policy content from leaking through public search, pages or sitemap; staff can use an explicitly no-indexed preview.
- Added migration `frontend.0012` plus seed migration `frontend.0013`, administrator procedures and five governance/privacy/publication contracts.
- Verified the live FAQ at desktop and 390 px mobile widths with no overflow, correct semantics/structured data and no browser console errors.
- Accepted baseline: migration drift clean, dependency integrity clean, Django and production deploy checks clean, local audit chain verified, and all 178 tests passed in 430.780 seconds.

## 2026-08-10 - PostgreSQL contention and migration reconciliation gates

- Added a true two-thread/two-connection PostgreSQL contract proving competing quotes for one room/date range serialize into exactly one active hold and one controlled rejection. SQLite skips the test; PostgreSQL-backed CI executes it.
- Added `reconcile_system`, producing machine-readable row counts and failing closed on pending migrations, overlapping blocking reservations/holds, completed payments without folio credits, refund overages, negative stock balances or audit-chain variance.
- The first reconciliation exposed two legacy completed payments without folios. Added idempotent migration `payments.0004` to attach/create the correct folio and post exactly one immutable payment credit per legacy record; post-migration reconciliation is clean.
- Added the reconciliation gate to PostgreSQL CI and pre/post migration plus isolated-restore procedures.
- A live dependency audit then identified six Django 4.2.30 vulnerabilities. Upgraded the supported runtime constraint to Django 5.2.16 through 5.2.x, installed 5.2.17, fixed the CI production-check MFA environment, and added an explicit CI PostgreSQL-vendor assertion plus dedicated contention-test step so a silent SQLite skip cannot pass the gate.
- Accepted local baseline under Django 5.2.17: migration drift, dependency integrity, vulnerability audit, Django/production checks, audit chain and system reconciliation passed; 182 tests ran in 727.692 seconds with 181 passing and the PostgreSQL-only contention contract intentionally skipped on local SQLite pending CI/staging execution evidence.

## 2026-08-10 - Vendor-neutral telemetry and static security gate

- Added OpenTelemetry zero-code instrumentation packages for Django/ASGI, PostgreSQL, Redis and outbound HTTP with OTLP HTTP/gRPC exporters, environment-defined sampling, service/environment resource identity and immutable releases.
- Structured JSON request logs now include release and, when a span is active, matching fixed-width trace/span identifiers for collector-to-log investigation.
- Production configuration fails closed without an OTLP endpoint and immutable release and rejects non-HTTPS remote collectors; CI supplies safe local placeholders and production deployments use the telemetry-wrapped Daphne command.
- Added an observability runbook covering deployment verification, privacy checks, collector-failure behavior and an owned initial alert matrix.
- Live console-exporter smoke evidence confirmed a real `/health/live/` Django server span with the supplied request ID, valid trace identity, route/status, service name and OpenTelemetry SDK/auto-instrumentation versions.
- Added medium/high-confidence Bandit analysis locally and in CI. The first scan found two unsafe generic URL-open boundaries; replaced them with an HTTPS/host/port/credential allowlist plus redirect validation for Brevo, covered by three SSRF-boundary tests. The repeated scan returned no medium/high findings.
- Accepted local baseline: 186 tests ran in 684.158 seconds with 185 passing and only the PostgreSQL-only contract skipped; migration drift, dependency integrity/vulnerability audit, production settings, audit chain, system reconciliation and medium/high static security analysis all passed.
