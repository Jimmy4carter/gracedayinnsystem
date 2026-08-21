# Incident Response Runbook

## Severity

- SEV-1: safety, confirmed data exposure, payment/ledger integrity, oversell or total outage.
- SEV-2: major workflow unavailable without safe workaround, Redis/worker outage or repeated email/print failure.
- SEV-3: isolated defect with controlled workaround.

## First 15 minutes

1. Assign incident, operations and communications leads.
2. Preserve release/time/reference evidence without secrets or full identity/payment data.
3. Contain via feature flag, job/integration disable or access restriction; do not delete evidence.
4. For suspected compromise, revoke credentials/tokens and notify qualified privacy/security owners.

## Scenario controls

- Booking conflict: stop allocation, preserve both references and reconcile before guest contact.
- Ledger mismatch: stop settlement; reconcile provider, payment, receipt, folio and cash movement; compensate rather than edit.
- Redis/WebSocket outage: use polling fallback, restore Redis/ASGI and verify transcripts.
- Brevo outage: let logged records retry; reconcile before manual resend.
- Printer outage: use numbered A4 receipt and log thermal reprint.
- Stuck audit: resolve reported exceptions; never alter snapshots or duplicate close.

Recover with targeted smoke tests, reconciliation and observation. Record cause, actions and owners; obtain incident-lead closure. Qualified advisers determine statutory notifications.

