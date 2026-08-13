# Backup and Restore Runbook

## Objectives

- Proposed RPO: 15 minutes with managed PostgreSQL PITR; encrypted logical backup daily.
- Proposed RTO: 4 hours. Business owner must approve both.
- Platform owner operates backups; another administrator verifies; management signs quarterly evidence.

## Create and verify

Keep `BACKUP_ENCRYPTION_KEY` in the secret manager, separate from database and storage credentials.

```powershell
python manage.py create_encrypted_backup --output-dir D:\GraceDayBackups
python manage.py verify_encrypted_backup --backup-file D:\GraceDayBackups\gracedayinn-YYYYMMDDTHHMMSSZ.dump.gdi
```

Upload the encrypted file and JSON manifest to versioned access-controlled storage. Proposed retention: daily 35 days, monthly 13 months, quarterly restore evidence 24 months, subject to approved privacy policy.

## Quarterly isolated restore

1. Provision isolated PostgreSQL with outbound integrations disabled.
2. Verify checksum/archive; decrypt only inside the isolated encrypted workspace.
3. Restore with `pg_restore --clean --if-exists --no-owner --no-privileges`.
4. Run migrations/checks and `python manage.py reconcile_system --json`; retain its migration, inventory, payment/refund, stock and audit evidence alongside the broader users, cash-movement and outbox/event counts.
5. Sample reservation → invoice → folio → payment → receipt and a manager pack.
6. Destroy plaintext/isolation under retention policy; retain signed counts, timings and exceptions.

For disaster recovery, freeze writes, select approved recovery point, prefer PITR, rotate potentially exposed credentials, and reconcile the recovery gap before reopening.
