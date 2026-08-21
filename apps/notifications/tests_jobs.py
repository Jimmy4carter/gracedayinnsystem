from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from .jobs import run_due_jobs
from .models import JobExecution, ScheduledJob


class ScheduledJobTests(TestCase):
    def test_due_job_is_claimed_recorded_and_rescheduled(self):
        ScheduledJob.objects.all().delete()
        job = ScheduledJob.objects.create(
            key='test-email-worker', handler='email_outbox', interval_minutes=5,
            next_run_at=timezone.now() - timedelta(minutes=1),
        )
        executions = run_due_jobs(limit=1, worker_id='test-worker')
        self.assertEqual(len(executions), 1)
        self.assertEqual(executions[0].status, 'succeeded')
        job.refresh_from_db()
        self.assertGreater(job.next_run_at, timezone.now())
        self.assertEqual(job.consecutive_failures, 0)
        self.assertIsNone(job.locked_at)

    def test_repeated_job_failure_enters_visible_paused_failure_state(self):
        ScheduledJob.objects.all().delete()
        job = ScheduledJob.objects.create(
            key='broken-worker', handler='unknown_handler', interval_minutes=1,
            next_run_at=timezone.now() - timedelta(minutes=1), max_failures=1,
        )
        executions = run_due_jobs(limit=1, worker_id='test-worker')
        self.assertEqual(executions[0].status, 'failed')
        job.refresh_from_db()
        self.assertFalse(job.is_enabled)
        self.assertEqual(job.consecutive_failures, 1)
        self.assertIn('Unknown scheduled-job handler', job.last_error)
        self.assertTrue(JobExecution.objects.filter(job=job, status='failed').exists())
