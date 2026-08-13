# Deployment and Rollback Runbook

## Pre-deployment

- Approved release/owner, CI green, no migration drift, dependency review, flags and rollback decision.
- Verify encrypted backup/PITR. Review migration locks and transformations.

## Release

```powershell
python manage.py check --deploy --settings=gracedayinn.settings.prod
python manage.py migrate --plan --settings=gracedayinn.settings.prod
python manage.py reconcile_system --json --settings=gracedayinn.settings.prod
python manage.py migrate --settings=gracedayinn.settings.prod
python manage.py reconcile_system --json --settings=gracedayinn.settings.prod
python manage.py collectstatic --noinput --settings=gracedayinn.settings.prod
```

Deploy ASGI and scheduler workers from the same immutable release. Require `/health/live/` and `/health/ready/` success, then smoke public quote, staff sign-in, front desk, management, chat fallback and queued email.

## Rollback and failed migration

- Prefer flag disable or application rollback when schema remains backward compatible.
- Never reverse destructive/data migrations without a tested reverse/reconciliation plan.
- Stop failed rollout, capture exact evidence, and do not fake migrations without proven schema equivalence.
- If restore is required, declare an incident, stop writes, follow the backup runbook and reconcile the gap.

Preserve both reconciliation JSON outputs with the release evidence. Any pending migration, overlapping blocking stay/hold, completed payment without its folio credit, refund overage, negative stock balance or audit-chain failure stops the release.

Record release/time/operator, migration output, reconciliation evidence, smoke results, job health, error/latency observation, rollback disposition and management approval.
