import socket
import uuid
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.frontend.reporting import generate_management_pack
from apps.reservations.pricing import expire_stale_holds

from .models import JobExecution, ScheduledJob
from .contacts import sync_brevo_contacts
from .alerts import evaluate_alert_rules
from .services import process_due_outbox


def _worker_id():
    return f'{socket.gethostname()}:{uuid.uuid4().hex[:8]}'


def _execute_handler(handler):
    if handler == 'email_outbox':
        return {'processed': len(process_due_outbox(limit=100))}
    if handler == 'brevo_contact_sync':
        return {'processed': len(sync_brevo_contacts(limit=100))}
    if handler == 'expire_inventory_holds':
        return {'expired': expire_stale_holds()}
    if handler == 'manager_pack':
        pack, created = generate_management_pack(business_date=timezone.localdate() - timedelta(days=1))
        return {'pack_id': pack.id, 'created': created, 'business_date': pack.business_date.isoformat()}
    if handler == 'domain_alerts':
        return evaluate_alert_rules()
    raise ValueError(f'Unknown scheduled-job handler: {handler}')


def run_due_jobs(*, limit=20, key=None, worker_id=None):
    worker_id = worker_id or _worker_id()
    completed = []
    ScheduledJob.objects.filter(
        locked_at__lt=timezone.now() - timedelta(minutes=30)
    ).update(locked_at=None, locked_by='', last_error='Recovered stale worker lock.')
    for _ in range(max(1, limit)):
        with transaction.atomic():
            due = ScheduledJob.objects.select_for_update().filter(
                is_enabled=True, next_run_at__lte=timezone.now(), locked_at__isnull=True,
            )
            if key:
                due = due.filter(key=key)
            job = due.order_by('next_run_at', 'id').first()
            if not job:
                break
            job.locked_at = timezone.now()
            job.locked_by = worker_id
            job.save(update_fields=['locked_at', 'locked_by', 'updated_at'])
            execution = JobExecution.objects.create(job=job, worker_id=worker_id)
        try:
            result = _execute_handler(job.handler)
        except Exception as exc:
            with transaction.atomic():
                locked = ScheduledJob.objects.select_for_update().get(pk=job.pk)
                locked.consecutive_failures += 1
                locked.last_error = str(exc)[:500]
                locked.last_run_at = timezone.now()
                locked.next_run_at = timezone.now() + timedelta(minutes=locked.interval_minutes)
                locked.locked_at = None
                locked.locked_by = ''
                if locked.consecutive_failures >= locked.max_failures:
                    locked.is_enabled = False
                locked.save()
                execution.status = 'failed'
                execution.error = str(exc)[:500]
                execution.finished_at = timezone.now()
                execution.save(update_fields=['status', 'error', 'finished_at'])
        else:
            with transaction.atomic():
                locked = ScheduledJob.objects.select_for_update().get(pk=job.pk)
                locked.consecutive_failures = 0
                locked.last_error = ''
                locked.last_run_at = timezone.now()
                locked.next_run_at = timezone.now() + timedelta(minutes=locked.interval_minutes)
                locked.locked_at = None
                locked.locked_by = ''
                locked.save()
                execution.status = 'succeeded'
                execution.result = result
                execution.finished_at = timezone.now()
                execution.save(update_fields=['status', 'result', 'finished_at'])
        completed.append(execution)
        try:
            from apps.frontend.audit import record_audit_event
            record_audit_event(
                event_type='system', action='scheduled_job_execution',
                target_model='JobExecution', target_id=execution.id,
                details={
                    'job_key': job.key, 'handler': job.handler,
                    'status': execution.status,
                    'result': execution.result if execution.status == 'succeeded' else {},
                    'error': execution.error if execution.status == 'failed' else '',
                    'worker_id': worker_id,
                },
            )
        except Exception:
            # Job execution remains authoritative even if the cross-domain audit sink is unavailable.
            pass
    return completed
