# System Administrator Runbook

## Audit integrity

- Run `python manage.py verify_audit_chain` after deployment, restore, suspected compromise and before producing audit evidence.
- A non-zero result or any sequence/hash/head mismatch is an integrity incident. Preserve the database and logs, restrict access, and follow the incident-response runbook; never rewrite records to make verification pass.
- Record the verified final sequence/hash in the approved external evidence store at the organization’s review cadence. This external checkpoint makes later whole-chain replacement detectable.

## Daily

- Review worker health, failed executions, Brevo contact/delivery exceptions and audit events.
- Confirm the latest encrypted backup manifest and monitoring alert.
- Review role changes, failed logins, OTP abuse and expiring manager packs.

## Access and configuration

- Provision least privilege; only administrators assign roles. Disable departed staff and retain history.
- Use named accounts. Production requires native staff MFA; verify enrollment before granting operational access.
- Reset a lost staff MFA device only after identity verification, using the MFA device admin action. The stated recovery reason and actor are retained in the tamper-evident audit chain.
- Maintain rates, taxes, extras, rooms, routing, chat hours, templates, flags and jobs through controlled surfaces.
- Publish local-guide entries and locale variants through the Frontend administration area. Verify journey estimates and outbound links before publishing.
- Moderate testimonials only when publication consent is recorded; reject content containing personal, sensitive, abusive or unverifiable claims. Never edit a guest's words to change their meaning.
- Maintain guest policies in Frontend > Policy documents. Replace placeholder text, set the effective date, record qualified review, then use Approve followed by Publish; never publish a placeholder or unreviewed legal wording. Any content, version or effective-date edit automatically withdraws the document and clears its approval, so repeat review and approval before republishing.
- Maintain concise, factual guest questions in Frontend > FAQ items. Confirm answers against current hotel operations before publishing and use display order to keep the most useful questions first.
- Never place secrets in admin fields, source control or tickets. Preview CMS content before publishing.

## Failed jobs

1. Inspect the failing job and immutable execution.
2. Correct credentials/provider/configuration without deleting evidence.
3. Re-enable an auto-paused job only after a safe test.
4. Run `python manage.py run_scheduled_jobs --key <job-key>` and confirm success.

Monthly: dependency/security review, inactive-account review, restore evidence, audit sample and retention queue.
