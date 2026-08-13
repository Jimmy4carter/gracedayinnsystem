# Product Requirements

## Product vision

GraceDay Inn will be one connected platform for hotel discovery, direct booking, guest service, front-desk operations, cashiering, housekeeping, management oversight, communications, and reporting.

## Product surfaces

### Public hotel website

- Brand-led responsive home page, accommodation catalog, room detail/gallery, amenities, dining/services, offers, local guide, about, policies, FAQs, blog/news, contact and inquiry pages.
- Search-engine metadata, schema.org hotel/room/offer markup, sitemap, accessible navigation, optimized media and editable content.
- Availability search with dates, occupants, promo code, room comparison and transparent price breakdown.
- Booking funnel: select room/rate, guest details, extras, policy acceptance, deposit/payment, confirmation and manage-booking access.
- Inquiry forms with categories, attachments where appropriate, consent capture, assignment, response status and SLA.
- Live chat launcher with business hours, queue/agent state, pre-chat form, transcript, inquiry conversion and escalation.
- Newsletter subscription with explicit consent, double opt-in as configured, preferences and unsubscribe.

### Guest portal

- Secure password setup/reset and optional MFA/passkey later.
- Upcoming/past stays, reservation details, payment/deposit status, downloadable invoices/receipts.
- Modify/cancel request based on policy; add arrival details, companion information and special requests.
- Pre-check-in, identity data, consent, service orders, messages/chat and feedback.
- Guests see only their own records and explicitly shared documents.

### Front desk and POS

- Fast “today” board for arrivals, in-house guests, departures, availability, dirty rooms and outstanding balances.
- Calendar/tape chart and room rack with drag-assisted room assignment subject to validation.
- Walk-in/phone/corporate booking, guest lookup/deduplication, room assignment, deposits, check-in, extension, move, checkout, no-show and cancellation.
- Folio posting for accommodation, services, taxes, fees, discount/adjustment with reason and approval.
- Cash/card/transfer/mobile-money tenders, split payment, refund/reversal, credit note and payment reference.
- Per-terminal cashier shift: opening float, paid-in/out, expected/actual cash, variance, supervisor close and Z-report.
- 80 mm thermal receipt and A4 invoice/registration card printing with reprint indicator and audit history.
- Keyboard-friendly interactions, clear destructive confirmations, duplicate-submit protection and fast guest search.

### Operations portals

- Housekeeping: room board, assigned task queue, clean/inspect status, issue reporting, photos, turnaround and supervisor verification.
- Maintenance: tickets, priority, asset/room, assignee/vendor, downtime, cost, evidence and return-to-service approval.
- Services/outlets: catalog, room-charge eligibility, orders, preparation/fulfilment, cancellation and folio posting.
- Reservations/sales: inquiries, quotes, holds, sources, corporate/group accounts, conversion tracking and follow-up.
- Communications: guest threads, templates, Brevo status/events, delivery failures, preferences and suppressions.

### Admin portal

Admin has full operational control through guarded capabilities, not an unconditional bypass. It includes users, roles, permissions, property configuration, inventory, rate plans, tax/fee rules, policies, templates, terminals, integrations, audit logs, data export, retention and system health. High-risk actions require re-authentication, reason capture and/or dual approval.

### Management portal

- Read-mostly executive dashboard across revenue, occupancy, ADR, RevPAR, booking pace, source mix, cancellations/no-shows, receivables, cashier variance, service SLAs, housekeeping turnaround and guest feedback.
- Drill-down from every metric to source records with consistent date/property filters.
- Daily manager report and night-audit pack; scheduled email/PDF/CSV distribution.
- Management query workflow: raise query against any report/transaction, assign owner, set priority/due date, discuss, attach evidence, resolve, reopen and retain audit history.
- Exceptions and alerts: unusual discounts/refunds, overdue balances, room-state conflicts, failed emails, unresolved inquiries, late tasks and integration failures.

## Core domain requirements

- Property, room type, physical room, amenity, image, sellable inventory date and operational room state.
- Rate plan, daily price, occupancy rules, inclusions, packages, promotion, taxes/fees, cancellation/deposit/no-show policy.
- Guest, contact methods, companions, identity information, preferences, consent, company/group account and duplicate resolution.
- Reservation with source, channel reference, status history, room assignment history, price snapshot and policy snapshot.
- Folio/ledger with immutable charge/payment/refund/adjustment entries and clear accounting date.
- Cashier terminal and shift, service outlet/order, housekeeping task, maintenance ticket, inquiry/case and communication event.
- Audit event and domain event/outbox for reliable integrations.

## Non-functional requirements

- Accessibility target: WCAG 2.2 AA for public, guest and primary staff workflows.
- Responsive public/guest experience; staff portal optimized for desktop/tablet with usable mobile task screens.
- Performance targets: public LCP under 2.5 s at the 75th percentile; common staff actions under 2 s excluding external providers.
- Availability target and recovery objectives must be approved before production; proposed V1: 99.5%, RPO 15 minutes, RTO 4 hours.
- Encrypt data in transit and at rest where infrastructure supports it; minimize identity/payment data; never store raw card data.
- All dates stored timezone-aware; property reporting follows the configured local timezone. Currency and money rounding are explicit.
- Retention, consent, subject-access/export and deletion/anonymization policies must be reviewed for applicable Nigerian privacy and fiscal requirements by qualified advisers.

## Explicit V1 exclusions unless approved

- Multi-property central reservation system, OTA/channel manager, door-lock integration, biometric attendance, full restaurant kitchen display, native mobile apps and full general-ledger accounting.
- Design the domain so these can be added, but do not delay the reliable single-property core.

## Success measures

- Direct booking conversion and abandonment by funnel step.
- Booking error/double-booking rate and payment reconciliation variance.
- Median check-in/check-out time and receipt print success rate.
- Occupancy, ADR and RevPAR with documented formulas.
- Inquiry first-response/resolution time; chat answer and conversion rate.
- Housekeeping turnaround and room-state discrepancy count.
- Email acceptance/delivery/bounce/complaint/unsubscribe rates.
- Permission violations, audit coverage, production error rate and recovery drill success.
