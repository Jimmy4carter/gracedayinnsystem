from django.core.exceptions import ValidationError
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from apps.notifications.models import Notification

from .guests import duplicate_guest_groups, merge_guest_accounts
from .models import GuestMergeHistory, GuestProfile, UserProfile


class GuestIdentityTests(APITestCase):
    def setUp(self):
        self.manager = UserProfile.objects.create_user(
            'guest-manager', password='test-pass', role='manager'
        )
        self.receptionist = UserProfile.objects.create_user(
            'guest-reception', password='test-pass', role='receptionist'
        )
        self.primary = UserProfile.objects.create_user(
            'ada-primary', email='Ada@Example.com', phone='0803 123 4567',
            first_name='Ada', role='guest', password='test-pass',
        )
        self.duplicate = UserProfile.objects.create_user(
            'ada-duplicate', email='ada@example.com', phone='+2348031234567',
            last_name='Lovelace', role='guest', password='test-pass',
        )
        GuestProfile.objects.create(user=self.primary, total_stays=1)
        GuestProfile.objects.create(user=self.duplicate, total_stays=2, notes='Late arrival')
        self.notification = Notification.objects.create(
            recipient=self.duplicate, title='Welcome', message='Hello',
        )

    def test_normalization_finds_candidates_and_merge_is_audited(self):
        self.assertEqual(self.primary.normalized_email, 'ada@example.com')
        self.assertEqual(self.primary.normalized_phone, '2348031234567')
        self.assertEqual(set(duplicate_guest_groups()), {self.primary, self.duplicate})

        history = merge_guest_accounts(
            primary_id=self.primary.id, duplicate_id=self.duplicate.id,
            actor=self.manager, reason='Verified matching email and phone at front desk.',
        )
        self.notification.refresh_from_db()
        self.primary.refresh_from_db()
        self.duplicate.refresh_from_db()
        self.assertEqual(self.notification.recipient, self.primary)
        self.assertEqual(self.primary.last_name, 'Lovelace')
        self.assertEqual(self.primary.guest_profile.total_stays, 3)
        self.assertFalse(self.duplicate.is_active)
        self.assertEqual(self.duplicate.merged_into, self.primary)
        self.assertEqual(self.duplicate.email, '')
        self.assertEqual(history.transferred_counts['notifications'], 1)
        with self.assertRaises(ValidationError):
            history.save()

    def test_receptionist_can_review_but_cannot_merge(self):
        self.client.force_authenticate(self.receptionist)
        response = self.client.get(reverse('user-duplicates'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        response = self.client.post(reverse('user-merge-guest', args=[self.primary.id]), {
            'duplicate_id': self.duplicate.id, 'reason': 'Suspected duplicate',
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_can_merge_through_api_and_portal(self):
        self.client.force_authenticate(self.manager)
        response = self.client.post(reverse('user-merge-guest', args=[self.primary.id]), {
            'duplicate_id': self.duplicate.id, 'reason': 'Identity verified by manager',
        })
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(GuestMergeHistory.objects.count(), 1)

        self.client.force_authenticate(user=None)
        self.client.force_login(self.manager)
        response = self.client.get(reverse('frontend:portal-guests'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertContains(response, 'Guest Directory')

    def test_portal_rejects_same_record_merge(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse('frontend:portal-guests'), {
            'command': 'merge_guest', 'primary_id': self.primary.id,
            'duplicate_id': self.primary.id, 'reason': 'Mistake',
        }, follow=True)
        self.assertContains(response, 'must be different')
        self.assertEqual(GuestMergeHistory.objects.count(), 0)
