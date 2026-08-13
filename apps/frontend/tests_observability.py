import json
import logging
from datetime import timedelta
from unittest.mock import Mock, patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.notifications.models import ScheduledJob
from gracedayinn.observability import JsonLogFormatter


class OperationalHealthTests(TestCase):
    def setUp(self):
        ScheduledJob.objects.update(next_run_at=timezone.now() + timedelta(minutes=5))

    def test_liveness_and_readiness_include_request_correlation(self):
        live = self.client.get(reverse('health-live'), HTTP_X_REQUEST_ID='probe-request-123')
        self.assertEqual(live.status_code, 200)
        self.assertEqual(live['X-Request-ID'], 'probe-request-123')
        ready = self.client.get(reverse('health-ready'))
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.json()['checks'], {
            'database': 'ok', 'cache': 'ok', 'scheduler': 'ok',
        })

    def test_readiness_fails_when_scheduler_is_stale(self):
        ScheduledJob.objects.filter(is_enabled=True).update(
            next_run_at=timezone.now() - timedelta(hours=2)
        )
        response = self.client.get(reverse('health-ready'))
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()['checks']['scheduler'], 'stale')
        self.assertTrue(response.json()['checks']['stale_jobs'])

    def test_invalid_request_id_is_replaced_and_logs_are_structured(self):
        response = self.client.get(reverse('health-live'), HTTP_X_REQUEST_ID='bad id with spaces')
        self.assertNotEqual(response['X-Request-ID'], 'bad id with spaces')
        record = logging.LogRecord(
            name='gracedayinn.request', level=logging.INFO, pathname='', lineno=1,
            msg='request_completed', args=(), exc_info=None,
        )
        record.request_id = 'structured-123'
        record.method, record.path, record.status_code = 'GET', '/health/live/', 200
        record.duration_ms, record.actor_id, record.event = 1.25, None, 'request_completed'
        payload = json.loads(JsonLogFormatter().format(record))
        self.assertEqual(payload['request_id'], 'structured-123')
        self.assertEqual(payload['status_code'], 200)
        self.assertNotIn('password', payload)
        self.assertNotIn('query', payload)

    def test_structured_logs_correlate_valid_distributed_trace(self):
        record = logging.LogRecord(
            name='gracedayinn.request', level=logging.ERROR, pathname='', lineno=1,
            msg='request_failed', args=(), exc_info=None,
        )
        context = Mock(is_valid=True, trace_id=0x1234, span_id=0x56)
        span = Mock()
        span.get_span_context.return_value = context

        with patch('gracedayinn.observability.trace.get_current_span', return_value=span):
            payload = json.loads(JsonLogFormatter().format(record))

        self.assertEqual(payload['trace_id'], '00000000000000000000000000001234')
        self.assertEqual(payload['span_id'], '0000000000000056')
        self.assertEqual(payload['release'], 'development')
