# Namecheap deployment and rollback runbook

## Pre-deployment gate

- Release is committed on `production`, reviewed, and pushed to `origin/production`.
- CI is green: MariaDB migration/concurrency test, full suite, production check, Bandit, and dependency audit.
- `makemigrations --check --dry-run` reports no drift.
- Encrypted MariaDB backup and manifest verify successfully for schema/finance changes.
- Brevo sender/domain, media storage, cron path, printer, and role-account handover have owners.

## Release

In **cPanel > Git Version Control > Manage** select **Update from Remote**, verify that `production` is checked out, then select **Deploy HEAD Commit**. `.cpanel.yml` runs the deployment hook and Passenger restart. Do not edit tracked production files with File Manager.

The hook must end with `Launch readiness passed` and `Deployment completed`. Record the deployed SHA and output.

## Post-release smoke

1. `/health/live/` and `/health/ready/` return success over HTTPS.
2. Public home, rooms, room detail, search/quote, OTP, and billboard render with static and uploaded images.
3. A guest booking confirms into an invoice; the payment link is visible; check-in rejects less than 50% and succeeds at 50% or more.
4. Open a cashier shift, record a cash payment, print/reprint a thermal receipt, close the shift, and verify its audit trail.
5. Confirm accountant VAT, journal balance, bank reconciliation, audit, charts, export, and manager report views.
6. Verify a Brevo message in both the portal delivery log and Brevo event history; do not treat API acceptance alone as delivery.
7. Verify the WhatsApp action opens the approved number, then verify inquiry routing, cron freshness, writable media, and the deployed SHA.

## Rollback

For code-only faults with a compatible schema, create a new revert commit and deploy normally:

```bash
git switch production
git pull --ff-only origin production
git revert BAD_COMMIT_SHA
git push origin production
```

Never use a hard reset as the normal production rollback. Never reverse a destructive/data migration without a tested reverse plan. If a database restore is required, declare an incident, stop writes, follow the backup runbook, deploy the matching code revision, run launch readiness/reconciliation, and account for every transaction in the recovery gap.

Preserve release SHA, operator/time, backup evidence, deployment output, smoke results, Brevo event, reconciliation JSON, errors, rollback decision, and management approval.
