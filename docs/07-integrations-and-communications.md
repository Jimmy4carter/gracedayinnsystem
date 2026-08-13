# Integrations and Communications Plan

## Brevo integration scope

Use Brevo through a provider adapter; domain workflows must not call Brevo directly.

### Transactional email

- Booking OTP/password setup, quote/hold expiry, confirmation, modification, cancellation, pre-arrival, payment receipt, invoice, checkout/thank-you, inquiry acknowledgement and staff alerts.
- Versioned branded templates with preview/test-send, plain-text alternative, locale, variables schema and approval/publish state.
- Send asynchronously from a transactional outbox. Store internal message ID, recipient reference, template version, purpose, Brevo message ID, attempt count, timestamps and final state.
- Retry only transient failures with backoff. Permanent failures create an exception task.

### Newsletter and lifecycle campaigns

- Store consent source, wording/version, timestamp, IP where appropriate, preferences and active/suppressed state locally.
- Sync contacts and attributes to Brevo idempotently. Resolve conflicts deliberately; unsubscribe/complaint suppression wins over local “active”.
- Support confirmed opt-in where business/legal policy requires it.
- Campaign authoring may live in Brevo for V1, but campaign identifiers and aggregate/per-recipient events needed for reporting must be synchronized.

### Webhooks and email metrics

- Verify webhook authenticity using the supported Brevo mechanism and deployment secret configuration.
- Persist raw-minimal event metadata once using unique provider event/message identifiers; process idempotently.
- Track accepted, delivered, deferred, soft/hard bounce, blocked, complaint, unsubscribe, open and click where available and permitted.
- Present counts with definitions. Opens/clicks are directional analytics, not proof a person read a message.
- Retain only data required for delivery, compliance, support and approved analytics.

## Suggested communication data model

- `Template`: key, channel, locale, schema, version, status, subject/body assets.
- `Message`: purpose, related object, recipient, template version, status, provider, provider ID.
- `DeliveryAttempt`: timestamps, response category, retry, error code/redacted detail.
- `DeliveryEvent`: provider event ID, normalized type and occurred/received times.
- `ContactPreference`: purpose/channel consent, source/version, granted/withdrawn times.
- `Suppression`: channel/address hash or protected value, reason, source and expiry if allowed.
- `CampaignSync`: internal/provider campaign and aggregate metrics.

## Live chat architecture

- Django Channels with authenticated WebSockets; Redis channel layer; HTTPS polling fallback.
- Anonymous visitors receive a short-lived conversation token. Verified guests bind only after secure authentication.
- Core records: conversation, participant, message, attachment, queue, assignment, status event, disposition and linked inquiry/reservation.
- Server authorizes every subscribe/send/read action; never trust a client-provided user or conversation ID.
- Agent inbox supports queue, unread count, assignment/transfer, internal notes, approved replies and related guest/stay context.
- Configure business hours, wait message, offline form, escalation timers and maximum attachment type/size.
- Sanitize content, scan attachments, rate-limit abuse and log moderation/security events.
- Define transcript retention and guest/staff access before launch.

## Inquiry management

- Public forms create a case and message, not merely an email.
- Categories: reservation, corporate/group, event, service, billing, complaint, general; configurable routing.
- Status: new, acknowledged, in progress, awaiting guest, resolved, closed, spam.
- Track first response, resolution, owner, SLA, priority, source, linked guest/reservation and outcome.
- Brevo sends acknowledgements/updates, while the case remains the operational source of truth.

## Payments and external services

- Select providers during Phase 0 based on Nigerian market requirements and current contracts.
- Never store card PAN/CVV. Prefer hosted checkout/tokenization and provider-certified terminals.
- Payment intents/attempts and webhooks require unique idempotency/provider keys and signature verification.
- A provider success event posts the internal ledger exactly once; mismatch enters reconciliation queue.
- Maintain daily settlement/import and unresolved discrepancy workflow.

## Integration acceptance tests

- Provider timeout before/after acceptance does not duplicate a booking, payment or email.
- Duplicate/out-of-order webhooks are harmless and converge to the correct state.
- Invalid webhook signatures are rejected and monitored.
- Brevo bounce/unsubscribe updates local suppression and prevents future marketing sends.
- Transactional messages remain permitted only according to approved purpose/preferences rules.
- Provider outage displays honest pending state and creates a retry/exception without losing the operation.
