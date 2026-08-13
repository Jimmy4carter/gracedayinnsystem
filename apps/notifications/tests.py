import json
import tempfile
from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.core import mail
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from asgiref.sync import async_to_sync
from channels.testing import WebsocketCommunicator
from django.test import TestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.frontend.models import NewsletterSubscription
from .contacts import enqueue_contact_sync, process_contact_sync
from .inquiries import add_inquiry_attachment, add_inquiry_reply, create_inquiry, transition_inquiry
from .chat import send_chat_message, start_conversation, submit_chat_satisfaction, transition_chat
from .models import (
    BrevoContactSync, ChatCannedReply, ChatOperatingHour, ContactPreference, DeliveryEvent, InquiryAttachment, InquiryRoutingRule,
    OutboundMessage, Suppression,
)
from .services import enqueue_email


class CommunicationOutboxTests(TestCase):
    @override_settings(
        EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
        EMAIL_DELIVERY_PROVIDER='django', EMAIL_OUTBOX_SEND_IMMEDIATELY=True,
    )
    def test_django_delivery_is_logged_and_idempotent(self):
        message, created = enqueue_email(
            purpose='booking_confirmation', recipient_email='guest@example.com',
            subject='Confirmed', html_body='<p>Confirmed</p>', text_body='Confirmed',
            idempotency_key='email-once',
        )
        replay, replay_created = enqueue_email(
            purpose='booking_confirmation', recipient_email='guest@example.com',
            subject='Confirmed', html_body='<p>Confirmed</p>', text_body='Confirmed',
            idempotency_key='email-once',
        )
        self.assertTrue(created)
        self.assertFalse(replay_created)
        self.assertEqual(replay.pk, message.pk)
        self.assertEqual(message.status, 'accepted')
        self.assertEqual(message.attempts.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    @override_settings(EMAIL_OUTBOX_SEND_IMMEDIATELY=False)
    def test_marketing_suppression_prevents_queue_delivery(self):
        Suppression.objects.create(email='optout@example.com', reason='unsubscribe')
        message, _ = enqueue_email(
            purpose='newsletter', recipient_email='optout@example.com', subject='Offer',
            html_body='<p>Offer</p>', marketing=True, idempotency_key='suppressed-email',
        )
        self.assertEqual(message.status, 'suppressed')
        self.assertEqual(message.attempt_count, 0)

    @override_settings(
        EMAIL_DELIVERY_PROVIDER='brevo', EMAIL_OUTBOX_SEND_IMMEDIATELY=True,
        BREVO_API_KEY='test-key', DEFAULT_FROM_EMAIL='hotel@example.com', BREVO_SANDBOX=True,
    )
    @patch('apps.notifications.services.open_brevo_request')
    def test_brevo_adapter_persists_provider_message_id(self, urlopen):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({'messageId': '<brevo-1>'}).encode()
        urlopen.return_value = response
        message, _ = enqueue_email(
            purpose='receipt', recipient_email='guest@example.com', subject='Receipt',
            html_body='<p>Receipt</p>', text_body='Receipt', idempotency_key='brevo-email',
        )
        self.assertEqual(message.status, 'accepted')
        self.assertEqual(message.provider_message_id, '<brevo-1>')
        request = urlopen.call_args.args[0]
        self.assertEqual(request.headers['Api-key'], 'test-key')
        self.assertEqual(request.headers['Idempotencykey'], 'brevo-email')


class BrevoContactSyncTests(TestCase):
    @override_settings(BREVO_API_KEY='contact-key', BREVO_CONTACT_LIST_ID=42)
    @patch('apps.notifications.contacts.open_brevo_request')
    def test_consent_and_suppression_are_synchronized_with_local_precedence(self, urlopen):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = json.dumps({'id': 321}).encode()
        urlopen.return_value = response
        NewsletterSubscription.objects.create(email='reader@example.com', is_active=True)
        ContactPreference.objects.create(
            email='reader@example.com', purpose='marketing', consent_granted=True,
            consent_source='website', granted_at=timezone.now(),
        )
        record = process_contact_sync(enqueue_contact_sync('reader@example.com').id)
        self.assertEqual(record.status, 'synced')
        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertFalse(payload['emailBlacklisted'])
        self.assertEqual(payload['listIds'], [42])
        self.assertTrue(payload['updateEnabled'])

        Suppression.objects.create(email='reader@example.com', reason='unsubscribe')
        record = process_contact_sync(enqueue_contact_sync('reader@example.com').id)
        self.assertEqual(record.status, 'suppressed')
        payload = json.loads(urlopen.call_args.args[0].data)
        self.assertTrue(payload['emailBlacklisted'])
        self.assertNotIn('listIds', payload)
        self.assertEqual(record.provider_contact_id, '321')

    @override_settings(BREVO_WEBHOOK_TOKEN='secret-webhook-token')
    def test_webhook_is_authenticated_idempotent_and_reconciles_unsubscribe(self):
        message = OutboundMessage.objects.create(
            purpose='newsletter', recipient_email='guest@example.com', subject='News',
            html_body='<p>News</p>', provider_message_id='<brevo-2>',
            idempotency_key='webhook-email', status='accepted',
        )
        payload = {
            'id': 91, 'event': 'unsubscribed', 'email': 'guest@example.com',
            'message-id': '<brevo-2>', 'ts': 1700000000,
        }
        url = '/api/webhooks/brevo/'
        self.assertEqual(self.client.post(url, payload, content_type='application/json').status_code, 401)
        first = self.client.post(
            url, payload, content_type='application/json',
            HTTP_X_BREVO_WEBHOOK_TOKEN='secret-webhook-token',
        )
        duplicate = self.client.post(
            url, payload, content_type='application/json',
            HTTP_X_BREVO_WEBHOOK_TOKEN='secret-webhook-token',
        )
        self.assertEqual(first.json()['processed'], 1)
        self.assertEqual(duplicate.json()['processed'], 0)
        self.assertEqual(DeliveryEvent.objects.count(), 1)
        self.assertTrue(Suppression.objects.filter(email='guest@example.com', reason='unsubscribe').exists())
        preference = ContactPreference.objects.get(email='guest@example.com', purpose='marketing')
        self.assertFalse(preference.consent_granted)


class InquiryWorkflowTests(TestCase):
    def setUp(self):
        self.agent = UserProfile.objects.create_user(
            username='inquiry-agent', role='receptionist', email='agent@example.com', password='test-pass'
        )

    @override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
    def test_case_has_sla_owner_history_and_logged_replies(self):
        case = create_inquiry(
            requester_name='Ada Guest', requester_email='ada@example.com',
            subject='Airport transfer', message='Can you arrange pickup?', category='service',
        )
        self.assertEqual(case.status, 'new')
        self.assertIsNotNone(case.first_response_due_at)
        self.assertEqual(case.messages.count(), 1)
        self.assertTrue(OutboundMessage.objects.filter(related_model='InquiryCase', related_id=str(case.id)).exists())
        case = transition_inquiry(case_id=case.id, action='acknowledge', actor=self.agent)
        self.assertEqual(case.owner, self.agent)
        transition_inquiry(case_id=case.id, action='start', actor=self.agent)
        reply = add_inquiry_reply(case_id=case.id, actor=self.agent, body='Yes, we can arrange this.')
        self.assertFalse(reply.is_internal)
        case = transition_inquiry(
            case_id=case.id, action='resolve', actor=self.agent, outcome='Pickup arranged'
        )
        self.assertEqual(case.status, 'resolved')
        self.assertEqual(case.history.count(), 4)
        self.assertEqual(OutboundMessage.objects.filter(purpose='inquiry_reply').count(), 1)

    def test_configurable_routing_assigns_owner_priority_and_sla(self):
        InquiryRoutingRule.objects.create(
            name='Billing duty manager', category='billing', source='website',
            priority='urgent', owner=self.agent, first_response_hours=1,
            resolution_hours=8, order=1,
        )
        before = timezone.now()
        case = create_inquiry(
            requester_name='Billing Guest', requester_email='billing@example.com',
            subject='Incorrect charge', message='Please review', category='billing', source='website',
        )
        self.assertEqual(case.owner, self.agent)
        self.assertEqual(case.priority, 'urgent')
        self.assertLessEqual(case.first_response_due_at, before + timedelta(hours=1, seconds=2))
        self.assertLessEqual(case.resolution_due_at, before + timedelta(hours=8, seconds=2))

    def test_attachment_validation_and_protected_download(self):
        guest = UserProfile.objects.create_user('attachment-guest', role='guest', password='pass')
        stranger = UserProfile.objects.create_user('attachment-stranger', role='guest', password='pass')
        case = create_inquiry(
            requester_name='Attachment Guest', requester_email='attach@example.com', requester=guest,
            subject='Evidence', message='Attached', category='complaint',
        )
        with tempfile.TemporaryDirectory() as media_root, self.settings(MEDIA_ROOT=media_root):
            attachment = add_inquiry_attachment(
                case=case, actor=self.agent,
                uploaded_file=SimpleUploadedFile('evidence.pdf', b'%PDF evidence', content_type='application/pdf'),
            )
            self.assertEqual(InquiryAttachment.objects.count(), 1)
            self.client.force_login(stranger)
            url = reverse('frontend:portal-inquiry-attachment-download', args=[attachment.id])
            self.assertEqual(self.client.get(url).status_code, 403)
            self.client.force_login(guest)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Disposition'], 'attachment; filename="evidence.pdf"')
            response.close()


class LiveChatWorkflowTests(TestCase):
    def setUp(self):
        self.agent = UserProfile.objects.create_user(
            username='chat-agent', role='receptionist', password='test-pass'
        )

    def test_visitor_token_agent_assignment_and_idempotent_messages(self):
        conversation = start_conversation(
            name='Visitor', email='visitor@example.com', body='<b>Hello</b>'
        )
        self.assertEqual(conversation.messages.get().body, 'Hello')
        client_id = 'ba167f70-58d6-42f4-8dca-e5a907e489b4'
        message, created = send_chat_message(
            conversation=conversation, visitor_token=conversation.visitor_token,
            body='Need a room', client_message_id=client_id,
        )
        replay, replay_created = send_chat_message(
            conversation=conversation, visitor_token=conversation.visitor_token,
            body='Need a room', client_message_id=client_id,
        )
        self.assertTrue(created)
        self.assertFalse(replay_created)
        self.assertEqual(message.pk, replay.pk)
        conversation = transition_chat(
            conversation_id=conversation.id, action='assign', actor=self.agent
        )
        self.assertEqual(conversation.assigned_to, self.agent)
        reply, _ = send_chat_message(
            conversation=conversation, actor=self.agent, body='I can help.'
        )
        self.assertEqual(reply.sender_type, 'agent')
        conversation = transition_chat(
            conversation_id=conversation.id, action='close', actor=self.agent,
            disposition='booking_assisted',
        )
        self.assertEqual(conversation.status, 'closed')

    def test_offline_chat_requires_email_and_creates_routed_case(self):
        ChatOperatingHour.objects.create(weekday=timezone.localdate().weekday(), is_closed=True)
        with self.assertRaises(ValidationError):
            start_conversation(name='Anonymous', body='Call me')
        conversation = start_conversation(
            name='Offline Visitor', email='offline@example.com', body='Please contact me'
        )
        self.assertTrue(conversation.is_offline_capture)
        self.assertEqual(conversation.status, 'waiting')
        self.assertIsNotNone(conversation.inquiry_id)
        self.assertEqual(conversation.inquiry.source, 'chat_offline')

    def test_closed_chat_accepts_one_sanitized_satisfaction_response(self):
        conversation = start_conversation(
            name='Feedback Visitor', email='feedback@example.com', body='Hello'
        )
        conversation = transition_chat(conversation_id=conversation.id, action='assign', actor=self.agent)
        conversation = transition_chat(
            conversation_id=conversation.id, action='close', actor=self.agent, disposition='resolved'
        )
        conversation = submit_chat_satisfaction(
            conversation=conversation, rating=5, comment='<b>Excellent</b>',
            visitor_token=conversation.visitor_token,
        )
        self.assertEqual(conversation.satisfaction_rating, 5)
        self.assertEqual(conversation.satisfaction_comment, 'Excellent')
        with self.assertRaises(ValidationError):
            submit_chat_satisfaction(
                conversation=conversation, rating=4, visitor_token=conversation.visitor_token,
            )

    def test_portal_uses_only_approved_canned_reply_and_tracks_usage(self):
        conversation = start_conversation(name='Reply Visitor', body='Do you have parking?')
        approved = ChatCannedReply.objects.create(
            title='Parking', category='facilities', body='Yes, secure parking is available.',
            status='approved', approved_by=self.agent, approved_at=timezone.now(),
        )
        draft = ChatCannedReply.objects.create(
            title='Draft answer', body='Unapproved content', status='draft',
        )
        self.client.force_login(self.agent)
        url = reverse('frontend:portal-chat-detail', args=[conversation.reference])
        page = self.client.get(url)
        self.assertContains(page, approved.title)
        self.assertNotContains(page, draft.title)
        response = self.client.post(url, {
            'command': 'reply', 'canned_reply_id': approved.id, 'body': 'Tampered browser value',
        })
        self.assertRedirects(response, url)
        approved.refresh_from_db()
        self.assertEqual(approved.use_count, 1)
        self.assertTrue(conversation.messages.filter(
            sender_type='agent', body='Yes, secure parking is available.',
        ).exists())
        response = self.client.post(url, {
            'command': 'reply', 'canned_reply_id': draft.id, 'body': 'Unapproved content',
        }, follow=True)
        self.assertContains(response, 'unavailable or not approved')
        self.assertFalse(conversation.messages.filter(body='Unapproved content').exists())


class LiveChatWebSocketTests(TransactionTestCase):
    def test_authorized_visitor_can_connect_and_send(self):
        conversation = start_conversation(name='Socket Visitor', body='Start')

        async def exercise():
            from gracedayinn.asgi import application
            communicator = WebsocketCommunicator(
                application,
                f'/ws/chat/{conversation.reference}/?token={conversation.visitor_token}',
            )
            connected, _ = await communicator.connect()
            self.assertTrue(connected)
            await communicator.send_json_to({
                'body': 'WebSocket message',
                'client_message_id': '88e0c498-aa02-4ca8-b209-1a054dc95845',
            })
            response = await communicator.receive_json_from()
            self.assertEqual(response['type'], 'message')
            self.assertEqual(response['body'], 'WebSocket message')
            await communicator.disconnect()

            denied = WebsocketCommunicator(application, f'/ws/chat/{conversation.reference}/?token=wrong')
            denied_connected, close_code = await denied.connect()
            self.assertFalse(denied_connected)
            self.assertEqual(close_code, 4403)

        async_to_sync(exercise)()

    def test_typing_and_presence_are_ephemeral_peer_events(self):
        conversation = start_conversation(name='Presence Visitor', body='Start')

        async def exercise():
            from gracedayinn.asgi import application
            url = f'/ws/chat/{conversation.reference}/?token={conversation.visitor_token}'
            first = WebsocketCommunicator(application, url)
            second = WebsocketCommunicator(application, url)
            self.assertTrue((await first.connect())[0])
            self.assertTrue((await second.connect())[0])
            presence = await first.receive_json_from()
            self.assertEqual(presence, {
                'type': 'presence', 'state': 'joined', 'participant': 'visitor',
            })
            await first.send_json_to({'type': 'typing', 'is_typing': True})
            typing = await second.receive_json_from()
            self.assertEqual(typing, {
                'type': 'typing', 'is_typing': True, 'participant': 'visitor',
            })
            await first.disconnect()
            left = await second.receive_json_from()
            self.assertEqual(left['type'], 'presence')
            self.assertEqual(left['state'], 'left')
            await second.disconnect()

        before = conversation.messages.count()
        async_to_sync(exercise)()
        self.assertEqual(conversation.messages.count(), before)
