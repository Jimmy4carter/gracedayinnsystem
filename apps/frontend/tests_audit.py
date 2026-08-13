from io import StringIO

from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.db import connection
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import UserProfile

from .audit import ZERO_HASH, verify_audit_chain
from .models import AuditLog


class TamperEvidentAuditTests(TestCase):
    def setUp(self):
        self.actor = UserProfile.objects.create_user(
            'audit-actor', password='pass', role='manager',
        )

    def _append(self, action, target_id='1'):
        return AuditLog.objects.create(
            actor=self.actor, event_type='security', action=action,
            target_model='TestRecord', target_id=target_id,
            details={'reason': 'controlled test'}, ip_address='127.0.0.1',
            user_agent='test-client',
        )

    def test_events_are_sequenced_chained_and_verifiable(self):
        first = self._append('first')
        second = self._append('second', '2')
        self.assertEqual(first.sequence, 1)
        self.assertEqual(first.previous_hash, ZERO_HASH)
        self.assertEqual(second.sequence, 2)
        self.assertEqual(second.previous_hash, first.event_hash)
        self.assertEqual(second.event_hash, second.calculate_hash())
        self.assertEqual(verify_audit_chain()['events_checked'], 2)
        output = StringIO()
        call_command('verify_audit_chain', stdout=output)
        self.assertIn('Audit chain verified: 2 event(s)', output.getvalue())

    def test_instance_queryset_bulk_and_actor_deletion_are_blocked(self):
        item = self._append('immutable')
        item.action = 'changed'
        with self.assertRaises(ValidationError):
            item.save()
        with self.assertRaises(ValidationError):
            AuditLog.objects.filter(pk=item.pk).update(action='changed')
        with self.assertRaises(ValidationError):
            AuditLog.objects.filter(pk=item.pk).delete()
        with self.assertRaises(ValidationError):
            AuditLog.objects.bulk_create([AuditLog(
                event_type='security', action='bulk', target_model='TestRecord',
            )])
        with self.assertRaises(ProtectedError):
            self.actor.delete()

    def test_out_of_band_hash_tampering_is_detected(self):
        item = self._append('detect-tampering')
        original_hash = item.event_hash
        with connection.cursor() as cursor:
            cursor.execute(
                'UPDATE frontend_auditlog SET event_hash = %s WHERE id = %s',
                ['f' * 64, item.id],
            )
        with self.assertRaisesMessage(ValidationError, 'event-hash mismatch'):
            verify_audit_chain()
        with connection.cursor() as cursor:
            cursor.execute(
                'UPDATE frontend_auditlog SET event_hash = %s WHERE id = %s',
                [original_hash, item.id],
            )
        self.assertEqual(verify_audit_chain()['events_checked'], 1)

    def test_authenticated_non_api_mutation_is_audited_without_request_payload(self):
        self.client.force_login(self.actor)
        response = self.client.post(reverse('frontend:subscribe-newsletter'), {
            'email': 'private-subscriber@example.com',
        })
        self.assertEqual(response.status_code, 302)
        event = AuditLog.objects.get(action='http_post')
        self.assertEqual(event.actor, self.actor)
        self.assertEqual(event.details['path'], reverse('frontend:subscribe-newsletter'))
        self.assertNotIn('private-subscriber@example.com', str(event.details))
        self.assertEqual(verify_audit_chain()['events_checked'], 1)
