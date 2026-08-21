# Current-State Audit

Audit date: 2026-08-09

## Executive assessment

The repository is a useful Django prototype, not yet a production hotel management system. It has a working domain skeleton, server-rendered public/portal templates, REST endpoints, role labels, a basic booking verification flow, reports, newsletters, and tests around selected portal workflows. Its largest risks are overly broad API permissions, incomplete hotel accounting/inventory concepts, unsafe concurrency assumptions, email delivery that is not production-integrated, and a generic visual/template layer.

Do not discard the project. Stabilize its foundation, preserve useful domain code, and expand it in controlled vertical slices.

## Technology and structure found

- Django 4.2 monolith with Django REST Framework and Simple JWT.
- Custom `UserProfile` based on `AbstractUser`.
- SQLite and console email backend configured by default.
- Server-rendered templates for public pages and staff/guest portals.
- Apps: accounts, rooms, reservations, billing, payments, services, housekeeping, notifications, frontend.
- PDF report generation via ReportLab and CSV report export.
- Static vendor bundles and a Soft UI dashboard theme are committed under `staticfiles/`.
- No production settings module, task queue, WebSocket layer, OpenAPI schema, CI workflow, container/deployment definition, or documented backup/recovery process was found.

## Existing capabilities

| Area | Current implementation | Assessment |
|---|---|---|
| Accounts | Admin, manager, receptionist, housekeeping, guest role field | Useful start; not granular RBAC |
| Rooms | Amenities, room types, physical rooms, operational status | Missing images/gallery, rate plans, restrictions, blocks, maintenance history |
| Reservations | Dates, occupants, state transitions, basic overlap checks in portal forms | Missing robust inventory locking, amendments, deposits, cancellation policy, source/channel |
| Guest records | Profile, identity fields, preferences and notes | Missing privacy lifecycle, companions, documents, stay history reconciliation |
| Billing | Invoice/items/receipts and tax calculation | Not yet a hotel folio/ledger; numbering and recalculation have integrity risks |
| Payments | Cash/card/transfer/mobile money states | No gateway, tender/session controls, refunds ledger, reconciliation or shift close |
| Services | Categories, menu items, service orders/items | A foundation for room service; not a complete POS/outlet model |
| Housekeeping | Tasks, priorities, assignment and lifecycle | Missing inspections, room-state reconciliation, linen/lost-and-found/maintenance separation |
| Notifications | In-app notification records | No event/outbox architecture or user delivery preferences |
| Public website | Home, rooms, details, offers, dining, laundry, blog, contact/search templates | Mixed real and static content; generic visual identity and incomplete CMS/content workflows |
| Booking | Website request, email OTP, account creation, pending reservation | Confirmation wording is misleading; no payment/deposit or transactional stock guarantee |
| Portal | Dashboards and operational pages with selected role decorators | Many views are broad; guest UX and management oversight need separation |
| Reporting | Selected KPIs, trends, CSV/PDF | Metric definitions and financial basis need formalization; no scheduled reports |
| Newsletter | Subscription and draft message models | No Brevo sync, campaign sending, consent evidence, events, suppression, or unsubscribe lifecycle |
| Audit | `AuditLog` used by selected frontend actions | Not comprehensive; API/admin/model changes can bypass it |
| Tests | Meaningful frontend workflow tests plus empty/near-empty app test modules | Critical API authorization, concurrency, accounting and integration tests absent |

## Critical findings

### P0 — repository does not currently boot

`python manage.py check` and `python manage.py test` both stop at `apps/accounts/models.py:1`: the import of `AbstractUser` is split into invalid Python syntax (`from django.contrib.auth.models` followed by `import AbstractUser`). The checked-in `.venv` is also not portable and points at a Python executable path that is unavailable on this machine. The source import must be corrected and the virtual environment recreated before the existing test claims can be trusted.

### P0 — authorization exposure

Most REST `ModelViewSet`s use only `IsAuthenticated`. An authenticated guest can potentially enumerate or mutate hotel-wide users, guests, rooms, reservations, invoices, invoice items, receipts, payments, service catalog/orders, and housekeeping tasks. Querysets also are not consistently scoped to the current guest or assigned staff member. Role checks in `apps/frontend/decorators.py` protect only selected HTML views.

Required response: introduce policy-based permissions, queryset scoping, field-level restrictions, object ownership tests, and default-deny rules before expanding API usage.

### P0 — booking and financial integrity

- Reservation numbers and invoice/receipt numbers use `count() + 1`, which can collide under concurrent requests or after deletion.
- Availability checks and reservation creation are not protected by a transactional inventory lock/database constraint.
- The API reservation serializer validates date order but does not check overlapping reservations.
- Room availability logic mixes physical room status with sellable inventory availability.
- Invoice totals depend on saving the invoice after item changes; item updates do not guarantee parent recalculation.
- Payment effects occur in `save()`, creating side-effect and retry/idempotency concerns.
- Receipts are separate records without a complete tender/refund/reversal trail.

Required response: PostgreSQL, transactional service methods, immutable ledger concepts, idempotency, sequence-safe identifiers, and explicit state machines.

### P0 — account and email security

- Public registration serializer accepts the `role` field, allowing role escalation unless constrained elsewhere.
- User endpoints expose all users to any authenticated caller.
- JWT logout attempts token blacklisting, but the blacklist app is not configured.
- Guest booking can surface a generated password in a success message and email. A password-set link is safer.
- OTP storage in the session lacks a documented expiry, retry limit, resend throttle, and attempt lockout.
- The email helper catches exceptions and prints them, so callers cannot reliably know delivery status.

### P1 — product gaps

- No management query/issue workflow with ownership, evidence, SLA and resolution.
- No real-time live chat model, agent inbox, routing, transcript, consent or handoff.
- No front-desk shift, cashier session, cash drawer, till variance, end-of-shift report or POS order model.
- No room-rate calendar, rate plans, promos, packages, taxes/fees configuration, deposits or cancellation policies.
- No group/corporate bookings, walk-ins, room moves, extensions, early/late checkout, no-shows, overbooking controls or waitlist.
- No formal folio with charges, adjustments, split payments, transfers, refunds, credit notes and reconciliation.
- No property configuration, outlet, terminal, printer, staff roster, maintenance, asset, inventory, minibar or night-audit modules.
- No CMS-grade control over pages, galleries, offers, FAQs, policies, SEO metadata or structured data.

## Code and maintainability observations

- `apps/frontend/views.py` combines public content, booking, staff operations, reports, email and audit helpers; split into domain/application services and smaller view modules.
- Business rules are duplicated between HTML views and REST API views.
- API actions permit invalid or insufficiently guarded transitions compared with some portal actions.
- Several endpoint names and README routes no longer precisely match actual `/portal/` routing.
- Static vendor/source archives and collected assets make repository navigation and dependency provenance difficult.
- Nigeria/Africa-Lagos operational assumptions are not represented: project timezone is UTC, currency/tax/receipt configuration is not explicit.

## Recommended disposition

Keep Django and server-rendered pages for version 1 unless a separate frontend is a confirmed business requirement. Move business behavior into tested application services, adopt PostgreSQL/Redis/Celery and Channels only where needed, and progressively replace template-theme UI with a purpose-built design system. This minimizes rewrite risk while supporting live updates and integrations.
