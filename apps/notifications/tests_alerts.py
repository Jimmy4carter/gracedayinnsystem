from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.housekeeping.models import HousekeepingTask, MaintenanceTicket
from apps.reservations.models import Reservation
from apps.rooms.models import Room, RoomType
from apps.frontend.models import AuditLog

from .alerts import evaluate_alert_rule, transition_alert
from .inquiries import create_inquiry
from .jobs import run_due_jobs
from .models import AlertRule, Notification, OperationalAlert, ScheduledJob


class OperationalAlertTests(TestCase):
    def setUp(self):
        self.manager = UserProfile.objects.create_user(
            'alert-manager', password='pass', role='manager', email='manager@example.com',
        )
        self.guest = UserProfile.objects.create_user(
            'alert-guest', password='pass', role='guest', email='guest@example.com',
        )
        room_type = RoomType.objects.create(name='Alert Room', base_price='10000', max_occupancy=2)
        self.room = Room.objects.create(number='ALERT-1', room_type=room_type, status='available')
        self.rule = AlertRule.objects.get(key='room-state')

    def _checked_in_reservation(self):
        today = timezone.localdate()
        return Reservation.objects.create(
            guest=self.guest, room=self.room, check_in_date=today,
            check_out_date=today + timedelta(days=1), nightly_rate='10000',
            total_amount='10000', status='checked_in', source='front_desk',
        )

    def test_discrepancy_is_deduplicated_notified_and_auto_resolved(self):
        self._checked_in_reservation()
        first = evaluate_alert_rule(self.rule)
        self.assertEqual(first['opened'], 1)
        alert = OperationalAlert.objects.get()
        self.assertEqual(alert.status, 'open')
        self.assertIn('checked-in stay', alert.detail)
        self.assertEqual(Notification.objects.filter(recipient=self.manager).count(), 1)

        second = evaluate_alert_rule(self.rule)
        alert.refresh_from_db()
        self.assertEqual(second['updated'], 1)
        self.assertEqual(alert.occurrence_count, 2)
        self.assertEqual(Notification.objects.filter(recipient=self.manager).count(), 1)

        self.room.status = 'occupied'
        self.room.save(update_fields=['status'])
        cleared = evaluate_alert_rule(self.rule)
        alert.refresh_from_db()
        self.assertEqual(cleared['resolved'], 1)
        self.assertEqual(alert.status, 'resolved')
        self.assertEqual(
            list(alert.history.values_list('action', flat=True)), ['detected', 'auto_resolve'],
        )

    def test_management_transition_requires_resolution_evidence_and_history_is_immutable(self):
        self._checked_in_reservation()
        evaluate_alert_rule(self.rule)
        alert = OperationalAlert.objects.get()
        transition_alert(alert_id=alert.id, action='acknowledge', actor=self.manager)
        with self.assertRaisesMessage(ValidationError, 'Resolution notes'):
            transition_alert(alert_id=alert.id, action='resolve', actor=self.manager)
        transition_alert(
            alert_id=alert.id, action='resolve', actor=self.manager,
            notes='Front desk reconciled room state.',
        )
        alert.refresh_from_db()
        self.assertEqual(alert.status, 'resolved')
        event = alert.history.last()
        event.notes = 'tampered'
        with self.assertRaises(ValidationError):
            event.save()

    def test_management_portal_exposes_and_controls_active_alert(self):
        self._checked_in_reservation()
        evaluate_alert_rule(self.rule)
        alert = OperationalAlert.objects.get()
        self.client.force_login(self.manager)
        url = reverse('frontend:portal-management')
        page = self.client.get(url)
        self.assertContains(page, str(alert.reference))
        response = self.client.post(url, {
            'command': 'alert_acknowledge', 'alert_id': alert.id,
        })
        self.assertRedirects(response, url)
        alert.refresh_from_db()
        self.assertEqual(alert.status, 'acknowledged')

    def test_scheduled_job_evaluates_seeded_rules(self):
        self._checked_in_reservation()
        job = ScheduledJob.objects.get(key='domain-alerts')
        job.next_run_at = timezone.now() - timedelta(seconds=1)
        job.save(update_fields=['next_run_at'])
        executions = run_due_jobs(key=job.key, limit=1, worker_id='alert-test')
        self.assertEqual(len(executions), 1)
        self.assertEqual(executions[0].status, 'succeeded')
        self.assertGreaterEqual(executions[0].result['opened'], 1)
        self.assertTrue(OperationalAlert.objects.filter(source_model='Room').exists())
        self.assertTrue(AuditLog.objects.filter(
            action='scheduled_job_execution', target_id=str(executions[0].id),
        ).exists())

    def test_seeded_domain_rules_detect_each_supported_operational_breach(self):
        old = timezone.now() - timedelta(hours=12)
        housekeeping = HousekeepingTask.objects.create(room=self.room, task_type='cleaning')
        HousekeepingTask.objects.filter(pk=housekeeping.pk).update(created_at=old)
        maintenance = MaintenanceTicket.objects.create(
            room=self.room, title='Air conditioner', description='Not cooling',
            downtime_required=False, reported_by=self.manager,
        )
        MaintenanceTicket.objects.filter(pk=maintenance.pk).update(updated_at=old)
        inquiry = create_inquiry(
            requester_name='SLA Guest', requester_email='sla@example.com',
            subject='Late reply', message='Please respond', category='general',
        )
        InquiryCase = inquiry.__class__
        InquiryCase.objects.filter(pk=inquiry.pk).update(
            first_response_due_at=timezone.now() - timedelta(minutes=1),
        )
        failing_job = ScheduledJob.objects.get(key='domain-alerts')
        failing_job.consecutive_failures = 3
        failing_job.last_error = 'Provider unavailable'
        failing_job.save(update_fields=['consecutive_failures', 'last_error'])

        expected_sources = {
            'housekeeping-overdue': 'HousekeepingTask',
            'maintenance-overdue': 'MaintenanceTicket',
            'inquiry-sla': 'InquiryCase',
            'job-failures': 'ScheduledJob',
        }
        for key, source_model in expected_sources.items():
            with self.subTest(rule=key):
                result = evaluate_alert_rule(AlertRule.objects.get(key=key))
                self.assertGreaterEqual(result['opened'], 1)
                self.assertTrue(OperationalAlert.objects.filter(
                    rule__key=key, source_model=source_model, status='open',
                ).exists())
        retired_chat_rule = AlertRule.objects.get(key='chat-unanswered')
        self.assertFalse(retired_chat_rule.is_enabled)
        self.assertEqual(evaluate_alert_rule(retired_chat_rule)['opened'], 0)
