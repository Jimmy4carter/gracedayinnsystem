# Privacy governance runbook

This runbook describes the controls implemented by GraceDay Inn. It is an operational draft, not legal advice. Qualified Nigerian privacy and fiscal advisers and the business owner must approve the policy, retention periods, notices, lawful bases, and exception handling before production launch.

## Roles and access

- Guests submit access/export, correction, or anonymization requests from **My Privacy**.
- Administrators and managers review and execute requests from **Privacy Requests**.
- Other staff roles cannot access the privacy queue or download artifacts.
- A guest can download only their own export. Managers and administrators can download an available export for controlled fulfilment.
- Legal holds are maintained on the guest record by authorized administrators. Record the authority, reason, scope, start date, reviewer, and release evidence in the approved case-management process.

## Request procedure

1. Verify the requester's identity using the approved procedure without collecting unnecessary identity data.
2. Inspect the request details and related guest record; reject unclear or invalid requests with a recorded reason.
3. Approve a valid request. The decision is added to immutable history.
4. For corrections, an authorized operator updates the verified source record and records what was corrected before completing the request.
5. Execute exports and anonymization only from the controlled management queue.
6. Give the requester the outcome through an approved channel and close any linked case.

Exports are generated as JSON and expire after seven days. They intentionally omit passwords, internal guest notes, internal inquiry notes, and internal chat messages. Treat every export as confidential, do not email it without an approved secure-delivery process, and remove expired artifacts from storage through the scheduled retention job once implemented.

## Anonymization controls

Execution is blocked while any of the following exists:

- a legal hold;
- a pending, confirmed, or checked-in reservation;
- a non-zero open folio.

When allowed, anonymization clears account identifiers, identity fragments, address, phone, profile preferences/notes, avatar, quote contact data, and linked inquiry/chat contact identifiers, sets an unusable password, and disables the account. Reservations, invoices, folios, payments, audit events, and their transaction references remain intact for operational and fiscal integrity. Marketing consent is withdrawn and the former address remains only in the suppression register to prevent accidental future contact.

## Proposed retention decision register

The owner and qualified advisers must replace every `TBD` before launch.

| Record class | Proposed operational rule | Final approval |
|---|---|---|
| Reservation, invoice, folio, payment and audit records | Retain for the approved fiscal/dispute period, then anonymize or dispose | TBD |
| Guest operational profile | Keep while needed for active service and approved relationship period | TBD |
| Inquiry and chat content | Short operational period, then delete or anonymize unless linked to a dispute | TBD |
| Consent and suppression evidence | Retain minimum evidence needed to prove preference and prevent contact | TBD |
| Privacy request history | Retain decision evidence for approved accountability period | TBD |
| Export artifact | Seven-day application availability; storage cleanup schedule required | TBD |
| Encrypted backups | Follow the backup runbook, reconciled with final privacy retention policy | TBD |

## Launch and recurring checks

- Obtain approved privacy notice, cookie/analytics notice, marketing wording, and consent versions.
- Define identity-verification evidence, statutory response deadlines, escalation owners, and breach-reporting workflow.
- Rehearse one export, correction, blocked anonymization, successful anonymization, and expired download in staging.
- Verify object storage is private, encrypted, access logged, and configured to delete expired artifacts.
- Review legal holds at an approved cadence and record releases; never release a hold solely to complete anonymization.
- Sample request history monthly for authorization, reasons, timeliness, and secure delivery.
- Review all data processors, including Brevo, hosting, payment, analytics, chat, and backup providers, before launch and after material change.
