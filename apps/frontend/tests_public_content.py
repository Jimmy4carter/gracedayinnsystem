from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.rooms.models import Room, RoomType

from .content import approve_policy, publish_policy, withdraw_policy
from .models import AuditLog, FAQItem, PolicyDocument


class PublicPolicyAndFAQTests(TestCase):
    def setUp(self):
        self.admin = UserProfile.objects.create_user(
            'policy-admin', password='pass', role='admin', is_staff=True,
        )
        self.manager = UserProfile.objects.create_user(
            'policy-manager', password='pass', role='manager', is_staff=True,
        )
        self.policy = PolicyDocument.objects.create(
            slug='test-booking-terms', policy_type='booking', title='Test booking terms',
            summary='Reviewed booking terms for test reservations.',
            body='These are the current reviewed booking terms.', version='2.0',
            effective_date=timezone.localdate(),
        )

    def test_policy_requires_admin_review_and_current_content_hash_before_publication(self):
        with self.assertRaises(ValidationError):
            approve_policy(policy_id=self.policy.id, actor=self.manager)
        with self.assertRaises(ValidationError):
            publish_policy(policy_id=self.policy.id, actor=self.admin)
        approved = approve_policy(
            policy_id=self.policy.id, actor=self.admin, notes='Owner-approved test copy.',
        )
        self.assertEqual(approved.review_status, 'approved')
        published = publish_policy(policy_id=self.policy.id, actor=self.admin)
        self.assertTrue(published.is_published)
        self.assertTrue(AuditLog.objects.filter(action='policy_approved').exists())
        self.assertTrue(AuditLog.objects.filter(action='policy_published').exists())

        published.body = 'Changed after approval.'
        published.save()
        published.refresh_from_db()
        self.assertFalse(published.is_published)
        self.assertEqual(published.review_status, 'draft')
        self.assertEqual(published.approved_hash, '')

    def test_drafts_are_hidden_but_staff_can_preview_with_noindex(self):
        public = self.client.get(reverse('frontend:public-policy-detail', args=[self.policy.slug]))
        self.assertEqual(public.status_code, 404)
        self.client.force_login(self.manager)
        preview = self.client.get(
            reverse('frontend:public-policy-detail', args=[self.policy.slug]), {'preview': '1'},
        )
        self.assertEqual(preview.status_code, 200)
        self.assertContains(preview, 'Staff preview')
        self.assertContains(preview, 'noindex,nofollow')

    def test_published_policy_appears_in_index_search_and_sitemap_then_withdraws(self):
        approve_policy(policy_id=self.policy.id, actor=self.admin)
        publish_policy(policy_id=self.policy.id, actor=self.admin)
        self.assertContains(self.client.get(reverse('frontend:public-policies')), self.policy.title)
        self.assertContains(
            self.client.get(reverse('frontend:public-search'), {'q': 'reviewed booking terms'}),
            self.policy.title,
        )
        sitemap = self.client.get(reverse('frontend:public-sitemap'))
        self.assertContains(sitemap, reverse('frontend:public-policy-detail', args=[self.policy.slug]))
        withdraw_policy(policy_id=self.policy.id, actor=self.admin, reason='Superseded for testing.')
        self.assertEqual(
            self.client.get(reverse('frontend:public-policy-detail', args=[self.policy.slug])).status_code,
            404,
        )

    def test_faq_schema_and_html_escape_untrusted_content(self):
        item = FAQItem.objects.create(
            category='booking', question='Can text close a script? </script>',
            answer='<script>alert("unsafe")</script>', display_order=1, is_published=True,
        )
        response = self.client.get(reverse('frontend:public-faq'))
        self.assertContains(response, 'Can text close a script?')
        body = response.content.decode()
        self.assertNotIn('<script>alert("unsafe")</script>', body)
        self.assertIn('\\u003c/script\\u003e', body)
        self.assertIn('application/ld+json', body)

    def test_public_search_never_queries_or_renders_internal_room_notes(self):
        room_type = RoomType.objects.create(name='Search-safe room', base_price='100.00')
        Room.objects.create(
            number='SAFE-1', room_type=room_type, description='',
            notes='PRIVATE-CODE-DO-NOT-EXPOSE',
        )
        response = self.client.get(
            reverse('frontend:public-search'), {'q': 'PRIVATE-CODE-DO-NOT-EXPOSE'},
        )
        self.assertNotContains(response, 'SAFE-1')
        self.assertFalse(response.context['room_results'].exists())
