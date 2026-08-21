# VAT, email and cPanel operations

## VAT control

Administrators manage VAT at `/portal/vat/`. Every change requires a reason and creates an append-only `VATRateChange` record containing the previous rate, new rate, administrator and effective time.

- A rate greater than zero is applied to new public quotes and new front-desk reservations.
- The rate and amount are copied into the booking and invoice snapshots.
- Existing quotes, reservations, invoices, receipts and payments are never repriced by a later change.
- A zero rate creates no VAT charge and VAT is omitted from public price breakdowns, A4 invoices, POS receipts and receipt emails.
- Legacy `TaxFee` records whose name/code identifies them as VAT are ignored after the central VAT control has been used, preventing duplicate VAT.

## Transactional email

Production email is queued and delivered through Brevo from `noreply@gracedayinn.com`. Booking verification, booking acknowledgement, staff invitation, password reset, newsletter, inquiry acknowledgement/reply and payment receipt email all use the shared text-only GraceDay header—no logo image is required.

Before launch:

1. Authenticate `gracedayinn.com` in Brevo and publish its SPF/DKIM records.
2. Verify `noreply@gracedayinn.com` as a Brevo sender.
3. Configure `BREVO_API_KEY`, `BREVO_WEBHOOK_TOKEN`, `DEFAULT_FROM_EMAIL` and `BREVO_SENDER_NAME`.
4. Configure the five-minute `run_scheduled_jobs` cron and test accepted/delivered webhook events.

## Deployment accounts

Production requires six unique password environment variables documented in `.env.example`. After migration, run:

```bash
python manage.py ensure_default_users
```

The command idempotently ensures these accounts exist: administrator, manager, reception, accountant, housekeeping and the `info@gracedayinn.com` test/guest account. Passwords are never stored in source control. Existing usable passwords are preserved; use normal password-reset/security procedures when rotating a deployed account.

For a local disposable environment only, `python manage.py ensure_default_users --generate-missing` prints strong one-time credentials. Do not use generated console output as a permanent production secret.
