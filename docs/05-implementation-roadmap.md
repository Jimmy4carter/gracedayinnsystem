# Implementation Roadmap

Estimates are relative and must be recalibrated after product workshops. Build vertical slices that include UI, policy, domain logic, audit, tests and observability.

## Phase 0 — decisions and baseline (1–2 weeks)

- Confirm single vs multi-property, currency, tax/service-charge rules, deposit/cancellation policy, payment providers, printer models, outlets and staff departments.
- Map current hotel workflows with front desk, cashier, housekeeping, management and finance.
- Approve role/capability matrix and metric catalog draft.
- Inventory current data and establish staging environment.
- Add CI, formatting/linting, test coverage reporting and dependency/security scanning.
- Record architecture decisions and define acceptance/UAT owners.

Exit: approved V1 scope, workflows, permission matrix, metric definitions, environments and prioritized backlog.

## Phase 1 — security and platform foundation (2–4 weeks)

- Close API authorization/role-escalation issues and scope every queryset.
- Add policy layer, secure onboarding/password setup, OTP expiry/throttling and comprehensive audit middleware/services.
- Introduce production settings, PostgreSQL, Redis, Celery, object storage abstraction and environment validation.
- Split oversized frontend views into domain services and consistent command handlers.
- Add safe identifiers, validation constraints, idempotency and state-machine rules.
- Add monitoring, structured logging, health checks, backup and restore automation.

Exit: no known critical auth exposure; critical legacy workflows pass policy tests; staging restore is demonstrated.

## Phase 2 — inventory, rates and booking engine (4–7 weeks)

- Build room gallery/content, rate plan, daily price, taxes/fees, policy versioning, promotions and extras.
- Build transactional availability/hold/allocation engine with concurrency tests.
- Redesign public discovery and mobile booking funnel.
- Add quote, deposit/payment handoff, confirmation, manage-booking and cancellation/change requests.
- Capture source, consent, pricing/policy snapshot and funnel analytics.
- Add CMS controls for core website pages, offers, FAQs, policies and SEO.

Exit: two concurrent requests cannot oversell controlled inventory; a complete direct booking is traceable end-to-end.

## Phase 3 — front desk, stay and cashiering (5–8 weeks)

- Build today board, tape chart/room rack, guest search/deduplication and walk-in/phone booking.
- Implement assignment, registration, check-in, room move, extension, no-show, cancellation and checkout commands.
- Replace invoice-first logic with folio/ledger, charge posting, taxes, adjustments, split settlement, refund/reversal and credit note.
- Add terminal/cashier shifts, floats, cash movements, variance approval, X/Z reports and reconciliation.
- Add receipt/A4 documents, print profiles, reprint audit and tested 80 mm print workflow.

Exit: front desk can operate a complete stay and close a cashier shift with reconciled, immutable financial history.

## Phase 4 — operations and service delivery (3–5 weeks)

- Upgrade housekeeping board, mobile task UX, inspections, room-state conflicts and automation after checkout.
- Add maintenance tickets, downtime, photos, vendors/costs and return-to-service approval.
- Upgrade service/outlet ordering and authorized folio posting.
- Add incident/lost-and-found/guest request workflows if approved for V1.

Exit: room readiness and operational tasks are owned, timed, auditable and reflected consistently at front desk.

## Phase 5 — Brevo, inquiries and live chat (3–5 weeks)

- Implement communication outbox, templates, event log, preferences, consent and suppressions.
- Integrate Brevo transactional email, contacts/newsletters and signed/idempotent event webhooks.
- Build inquiry/case inbox with routing, SLA, templates and escalation.
- Build WebSocket live chat, queue/assignment, agent UI, offline capture, transcript and conversion links.
- Add delivery and chat analytics with privacy controls.

Exit: transactional messages retry safely and are traceable; staff can handle and escalate inquiries/chat in one portal.

## Phase 6 — management, reporting and automation (3–6 weeks)

- Approve/implement metric catalog: occupancy, ADR, RevPAR, revenue, receivables, pace, sources, cancellations, SLAs and variances.
- Build management overview with drill-down, filters, alerts and exception queues.
- Add management query cases, evidence, assignment, SLA, resolution and escalation.
- Implement night audit/business date, daily manager pack, scheduled reports and controlled exports.
- Add configurable automations with safe defaults and failure queues.

Exit: every headline metric reconciles to source records and managers can raise/close audited queries.

## Phase 7 — experience hardening and launch (3–5 weeks)

- Complete design system and visual overhaul across public, guest and staff experiences.
- Accessibility, responsive, cross-browser, performance and printer-device testing.
- Penetration test/remediation, privacy/retention review and payment-scope review.
- Data migration rehearsal, staff training, runbooks, UAT, rollback rehearsal and launch support plan.
- Soft launch with feature flags and hypercare dashboards.

Exit: UAT sign-off, performance/security thresholds met, restore/rollback proven, trained owners and production readiness approval.

## Suggested release slices

- Release A: secure current portal and production foundation.
- Release B: modern public website plus reliable direct booking.
- Release C: front desk, folio, cashier shift and thermal receipt.
- Release D: operations, communications/live chat and management intelligence.

Do not promise calendar dates until Phase 0 decisions and team capacity are known.
