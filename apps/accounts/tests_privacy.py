import json
import tempfile
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.frontend.models import NewsletterSubscription
from apps.notifications.models import ContactPreference, Suppression

from .models import DataPrivacyRequestHistory, GuestProfile, UserProfile
from .privacy import execute_privacy_request, review_privacy_request, submit_privacy_request


class PrivacyWorkflowTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(MEDIA_ROOT=self.media.name)
        self.settings_override.enable()
        self.guest = UserProfile.objects.create_user(
            username='privacy-guest', password='test-pass', role='guest',
            email='guest@example.com', first_name='Ada', last_name='Guest', phone='08012345678',
        )
        GuestProfile.objects.create(user=self.guest, preferences='Quiet room', notes='Private note')
        self.manager = UserProfile.objects.create_user(
            username='privacy-manager', password='test-pass', role='manager', email='manager@example.com',
        )

    def tearDown(self):
        self.settings_override.disable()
        self.media.cleanup()

    def test_guest_export_is_reviewed_downloadable_and_excludes_internal_profile_notes(self):
        self.client.force_login(self.guest)
        response = self.client.post(reverse('frontend:portal-privacy'), {
            'command': 'submit', 'request_type': 'export', 'details': 'My records',
        })
        self.assertRedirects(response, reverse('frontend:portal-privacy'))
        item = self.guest.privacy_requests.get()
        review_privacy_request(request_id=item.id, action='approve', actor=self.manager)
        execute_privacy_request(request_id=item.id, actor=self.manager)
        item.refresh_from_db()

        response = self.client.get(reverse('frontend:portal-privacy-download', args=[item.id]))
        payload = json.loads(b''.join(response.streaming_content))
        response.close()
        self.assertEqual(payload['profile']['email'], 'guest@example.com')
        self.assertNotIn('password', payload['profile'])
        self.assertNotIn('notes', payload['profile'])
        self.assertEqual(list(item.history.values_list('action', flat=True)), ['submit', 'approve', 'execute'])

    def test_export_access_is_owner_or_manager_only_and_expiry_is_enforced(self):
        item = submit_privacy_request(guest=self.guest, request_type='export')
        review_privacy_request(request_id=item.id, action='approve', actor=self.manager)
        execute_privacy_request(request_id=item.id, actor=self.manager)
        stranger = UserProfile.objects.create_user(
            username='other-guest', password='test-pass', role='guest', email='other@example.com',
        )
        self.client.force_login(stranger)
        self.assertEqual(
            self.client.get(reverse('frontend:portal-privacy-download', args=[item.id])).status_code, 403,
        )
        item.artifact_expires_at = timezone.now() - timedelta(seconds=1)
        item.save(update_fields=['artifact_expires_at'])
        self.client.force_login(self.manager)
        self.assertEqual(
            self.client.get(reverse('frontend:portal-privacy-download', args=[item.id])).status_code, 404,
        )

    def test_anonymization_honors_legal_hold_and_suppresses_marketing(self):
        NewsletterSubscription.objects.create(email=self.guest.email)
        ContactPreference.objects.create(
            email=self.guest.email, purpose='marketing', consent_granted=True,
            consent_source='website', granted_at=timezone.now(),
        )
        item = submit_privacy_request(guest=self.guest, request_type='anonymize')
        review_privacy_request(request_id=item.id, action='approve', actor=self.manager)
        self.guest.privacy_legal_hold = True
        self.guest.save(update_fields=['privacy_legal_hold'])
        with self.assertRaisesMessage(ValidationError, 'legal hold'):
            execute_privacy_request(request_id=item.id, actor=self.manager)

        self.guest.privacy_legal_hold = False
        self.guest.save(update_fields=['privacy_legal_hold'])
        execute_privacy_request(request_id=item.id, actor=self.manager)
        self.guest.refresh_from_db()
        self.assertFalse(self.guest.is_active)
        self.assertEqual(self.guest.email, '')
        self.assertIsNotNone(self.guest.anonymized_at)
        self.assertFalse(NewsletterSubscription.objects.get(email='guest@example.com').is_active)
        self.assertFalse(ContactPreference.objects.get(email='guest@example.com').consent_granted)
        self.assertTrue(Suppression.objects.filter(email='guest@example.com').exists())

    def test_duplicate_active_request_and_history_mutation_are_rejected(self):
        item = submit_privacy_request(guest=self.guest, request_type='correction', details='Fix my name')
        with self.assertRaises(ValidationError):
            submit_privacy_request(guest=self.guest, request_type='correction')
        event = item.history.get()
        event.notes = 'changed'
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            DataPrivacyRequestHistory.objects.get(pk=event.pk).delete()

    def test_non_management_staff_cannot_open_privacy_queue(self):
        receptionist = UserProfile.objects.create_user(
            username='frontdesk', password='test-pass', role='receptionist',
        )
        self.client.force_login(receptionist)
        self.assertEqual(self.client.get(reverse('frontend:portal-privacy')).status_code, 403)
