# Target Architecture

## Recommended approach

Evolve the Django monolith into a modular monolith. Keep one deployable application for V1, but enforce domain boundaries and move business rules out of views/models into application services. Add infrastructure only for proven needs.

## Runtime components

- Django 5.2 LTS, kept within the supported security patch line by the dependency audit gate.
- PostgreSQL as the system of record, using transactions, row locks, constraints and database indexes.
- Redis for cache, rate limits, short-lived booking holds and async transport.
- Celery workers and scheduler for Brevo sends, webhook processing, scheduled reports, housekeeping automation and retries.
- Django Channels/WebSockets for live chat and selected portal updates; retain polling fallback.
- S3-compatible object storage for room media, report artifacts and controlled attachments.
- Reverse proxy/CDN, TLS, secure cookies, CSP and compressed/versioned assets.
- Error monitoring, structured logs, metrics, traces and uptime checks.

## Proposed Django domains

| Domain | Responsibilities |
|---|---|
| `identity` | Users, roles, capabilities, sessions, MFA, staff/property assignments |
| `properties` | Hotel configuration, rooms, room types, amenities, operational blocks |
| `rates` | Rate plans, daily prices, restrictions, offers, taxes/fees and policy versions |
| `inventory` | Sellable room-type inventory, holds, allocations and availability service |
| `guests` | Guest identity, companions, preferences, consents and deduplication |
| `reservations` | Quotes, bookings, amendments, assignments, stays and state history |
| `folios` | Folios, immutable ledger entries, invoices, credit notes and receipts |
| `payments` | Payment attempts, tenders, refunds, reconciliation and provider webhooks |
| `cashiering` | Terminals, shifts, floats, cash movements, close/Z reports and print jobs |
| `housekeeping` | Room cleaning lifecycle, assignments, inspections and discrepancy tracking |
| `maintenance` | Tickets, assets, downtime, costs and return to service |
| `services` | Outlets, catalog, orders, fulfillment and charge posting |
| `crm` | Inquiries, cases, management queries, guest threads and follow-ups |
| `communications` | Templates, messages, Brevo contacts/campaign events, preferences/suppressions |
| `reporting` | Metric definitions, read models, scheduled packs and controlled exports |
| `audit` | Append-only security and business audit events |
| `content` | Public pages, media, offers, FAQs, blog and SEO fields |

Existing apps can be migrated incrementally; do not rename everything in one risky change.

## Application pattern

- Views/serializers/forms parse input and call command/query services.
- Commands enforce policy and state transitions inside `transaction.atomic()`.
- Domain services return typed results and emit domain events to an outbox in the same transaction.
- Workers deliver outbox events idempotently to Brevo, notifications, analytics and scheduled processes.
- Queries use scoped selectors/read models and never rely on template-only filtering.
- Model/database constraints protect invariants even when code paths fail.

## Data integrity decisions

- Use UUID primary/public identifiers where enumeration is undesirable; retain human-friendly sequence numbers from a safe sequence/table.
- Prevent overlapping confirmed/occupied allocations transactionally. Inventory is by room type until physical assignment when business rules allow.
- Store quoted price, taxes, inclusions and policies as reservation snapshots.
- Represent money with currency plus fixed decimal rules; centralize rounding.
- Folio balance is derived from immutable ledger entries. Corrections are compensating entries.
- External requests/webhooks use idempotency keys and unique provider event IDs.
- Use explicit state history tables for reservations, payments, rooms, tasks, queries and communications.

## API and security architecture

- Version API routes (`/api/v1/`) and publish an OpenAPI contract.
- Browser pages prefer secure session authentication; JWT is for documented external/mobile clients.
- Central policy functions cover role, scope, property membership, object ownership, state and thresholds.
- Restrict serializer writable fields by command; never expose `fields='__all__'` for sensitive write APIs.
- Rate-limit authentication, OTP, booking, inquiry, chat and webhook endpoints.
- Password setup uses expiring single-use links; staff invites and resets are logged.
- Secrets live in deployment secret storage; rotate credentials and webhook signing secrets.

## Printing architecture

Use browser print CSS as the first reliable V1 path for standard 80 mm printers:

- Dedicated receipt route and `@media print` layout with configurable 58/80 mm width.
- Receipt content generated from issued immutable data, with QR/reference and reprint metadata.
- Terminal profile controls printer width, copies, header/footer and auto-print preference.
- Where browsers cannot print silently, add a later local print bridge/agent with authenticated short-lived signed jobs. Do not weaken browser security or depend on vendor-specific commands in the core domain.

## Reporting architecture

- Create a metric catalog defining formula, time basis, inclusions/exclusions, currency and drill-down source.
- Transactional tables remain authoritative; materialized/read tables support expensive dashboards.
- Night audit freezes an operational business date and produces a reproducible daily pack.
- Exports run asynchronously when large, expire after a configured period and are audited.

## Migration strategy

1. Add safety tests around current behavior.
2. Introduce policies and services behind existing routes.
3. Migrate SQLite data to PostgreSQL in staging and reconcile record counts/totals.
4. Add new ledger/inventory models alongside legacy billing/reservation fields.
5. Backfill and reconcile, then switch reads and writes by feature flag.
6. Remove legacy fields only after production validation and rollback window.
