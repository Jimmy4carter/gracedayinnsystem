# MariaDB backup and restore runbook

## Objectives and ownership

- Target RPO: 24 hours until an off-host schedule is proven; improve to six hours if cPanel resource limits permit.
- Target RTO: four hours after a rehearsed restore.
- The administrator schedules and monitors backups, a second administrator verifies them, and management signs quarterly restore evidence.
- Keep `BACKUP_ENCRYPTION_KEY` separate from database, cPanel, and storage credentials.

## Create, verify, and retain

Run with production settings and an output directory outside the repository:

```bash
python manage.py create_encrypted_backup --output-dir /home/CPANEL_USERNAME/private_backups
python manage.py verify_encrypted_backup \
  --backup-file /home/CPANEL_USERNAME/private_backups/gracedayinn-YYYYMMDDTHHMMSSZ.sql.gdi
```

The command uses `mysqldump --single-transaction --quick --skip-lock-tables` with `utf8mb4`, never places the database password in process arguments, encrypts the SQL with authenticated AES-256-GCM, writes a checksum manifest, and removes plaintext temporary data. `MYSQL_DUMP_BINARY` may override the utility path when cPanel does not expose `mysqldump` normally.

Copy both `.sql.gdi` and its `.json` manifest to access-controlled storage outside the hosting account. Recommended retention, subject to the final privacy policy: daily 35 days, monthly 13 months, and quarterly restore evidence 24 months. A backup remaining only on the same Namecheap account is not disaster recovery.

## Before a schema or finance release

1. Run `reconcile_system --json` and retain the clean result.
2. Create and verify an encrypted application backup.
3. Also create a cPanel database backup if available.
4. Record the release SHA, database name, backup filename/checksum, operator, and UTC timestamp.
5. Do not deploy if verification fails.

## Quarterly isolated restore

1. Create a separate MariaDB database/user and disable outbound Brevo delivery in the restore environment.
2. Run `verify_encrypted_backup` before decrypting.
3. Decrypt only in a private temporary directory using the project backup helper or an approved recovery procedure.
4. Restore with the server's MariaDB client: `mysql -u RESTORE_USER -p RESTORE_DATABASE < restored.sql`.
5. Point an isolated application instance at the restored database and run migrations, `check --deploy`, `launch_readiness`, and `reconcile_system --json`.
6. Sample reservation → invoice → journal → payment → receipt, VAT history, cashier shift, bank reconciliation, email log, and manager report records.
7. Record counts, timings, exceptions, and sign-off. Securely remove plaintext SQL and destroy the isolated database after approval.

For disaster recovery, freeze writes, select the approved recovery point, rotate possibly exposed credentials, restore the matching code revision, reconcile the recovery gap, and obtain management approval before reopening.
