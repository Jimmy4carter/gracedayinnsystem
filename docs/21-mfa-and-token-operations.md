# MFA and Token Operations

## Staff enrollment

Production sets `STAFF_MFA_REQUIRED=True`. After a staff password is accepted, an account without a confirmed device is held in a five-minute pre-authentication session and sent to `/portal/mfa/enroll/`. The staff member adds the displayed setup key to a TOTP authenticator, confirms a six-digit code, and stores the eight one-use recovery codes in an approved password manager.

Staff can open **Security / MFA** in the portal to verify enrollment and see the number of recovery codes remaining. Secrets are encrypted at rest with `MFA_ENCRYPTION_KEY`; recovery codes are stored only as password hashes. Never log or copy setup keys, current codes, or recovery codes into support tickets.

## Verification controls

- TOTP codes use a 30-second window and cannot be replayed.
- A one-window clock tolerance is accepted.
- Recovery codes are one-use and are removed atomically after verification.
- Repeated invalid attempts temporarily lock MFA verification according to `MFA_MAX_ATTEMPTS` and `MFA_LOCK_MINUTES`.
- Staff portal and staff API authentication enforce the same device and code policy. Guest authentication does not require staff MFA.
- Enrollment, successful and failed verification, resets, login, and logout are written to the audit trail.

## Lost device and controlled recovery

Only an administrator can reset MFA. Verify the staff member's identity through the approved offline procedure, select the device in **Admin > Accounts > Staff MFA devices**, run the reset action, and provide a meaningful reason. The next successful password sign-in requires fresh enrollment. Do not delete the user account or edit MFA database fields directly.

After suspected compromise, also deactivate the account until credentials are changed, revoke active sessions/tokens, review authentication and MFA audit events, and follow the incident-response runbook.

## JWT lifecycle

- Access tokens expire after 15 minutes.
- Refresh tokens expire after seven days and rotate on refresh.
- Rotated and explicitly logged-out refresh tokens are blacklisted.
- API logout requires a valid refresh token and records the event; invalid or missing tokens are rejected.
- Purge expired token rows with SimpleJWT's `flushexpiredtokens` command from a controlled scheduled maintenance job.

## Key management

Set a unique random `MFA_ENCRYPTION_KEY` of at least 32 characters through the production secret store. Losing or changing this key without a planned migration makes enrolled TOTP secrets undecryptable. Key rotation therefore requires a controlled re-enrollment campaign or a dedicated decrypt/re-encrypt migration with both old and new keys available. Never commit the key.

## Verification

Run:

```powershell
.\.venv\Scripts\python.exe manage.py test apps.accounts.tests_mfa
.\.venv\Scripts\python.exe manage.py verify_audit_chain
```

Confirm that production deployment checks reject a missing/short MFA key and that all staff are enrolled before cutover.
