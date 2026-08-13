import json
import re
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.test import override_settings
from django.core import mail
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import GuestProfile, UserProfile
from apps.billing.models import Invoice, InvoiceItem
from apps.housekeeping.models import HousekeepingTask, MaintenanceTicket
from apps.notifications.models import Notification
from apps.payments.models import CashierTerminal, Payment
from apps.payments.services import open_cashier_shift
from apps.reservations.models import Reservation
from apps.rooms.models import Room, RoomType
from apps.services.models import MenuItem, ServiceCategory, ServiceOrder, ServiceOrderItem

from .forms import BookingRequestForm
from .models import AuditLog


class FrontendWorkflowTests(TestCase):
	def _create_role_user(self, username, role):
		user = UserProfile.objects.create_user(
			username=username,
			role=role,
			email=f'{username}@example.com',
		)
		user.set_password(self.test_secret)
		user.save(update_fields=['password'])
		return user

	def setUp(self):
		cache.clear()
		self.test_secret = 'test-secret-frontend'
		self.room_type = RoomType.objects.create(
			name='Deluxe Suite',
			description='Test room type',
			base_price=Decimal('42000.00'),
			max_occupancy=2,
		)
		self.room = Room.objects.create(
			number='101',
			room_type=self.room_type,
			floor=1,
			status='available',
			is_active=True,
		)
		self.guest = UserProfile.objects.create_user(
			username='guest01',
			role='guest',
			email='guest01@example.com',
		)
		self.guest.set_password(self.test_secret)
		self.guest.save(update_fields=['password'])
		self.staff = UserProfile.objects.create_user(
			username='frontdesk',
			role='receptionist',
			email='frontdesk@example.com',
		)
		self.staff.set_password(self.test_secret)
		self.staff.save(update_fields=['password'])
		self.admin = self._create_role_user('admin01', 'admin')
		self.manager = self._create_role_user('manager01', 'manager')
		self.housekeeper = self._create_role_user('housekeeper01', 'housekeeping')
		self.other_guest = self._create_role_user('guest02', 'guest')
		self.service_category = ServiceCategory.objects.create(name='Restaurant')
		self.menu_item = MenuItem.objects.create(
			category=self.service_category,
			name='Jollof Rice',
			price=Decimal('6500.00'),
			is_available=True,
		)
		self.role_users = {
			'admin': self.admin,
			'manager': self.manager,
			'receptionist': self.staff,
			'housekeeping': self.housekeeper,
			'guest': self.guest,
		}

	def test_staff_can_create_room_from_portal(self):
		self.client.force_login(self.staff)
		response = self.client.post(
			reverse('frontend:portal-rooms'),
			data={
				'number': '205',
				'room_type': self.room_type.id,
				'floor': 2,
				'status': 'available',
				'description': 'New deluxe room',
				'notes': 'Ready for deployment',
				'is_active': 'on',
			},
		)

		self.assertEqual(response.status_code, 302)
		self.assertTrue(Room.objects.filter(number='205').exists())

	def test_staff_can_create_guest_from_portal(self):
		self.client.force_login(self.staff)
		response = self.client.post(
			reverse('frontend:portal-guests'),
			data={
				'username': 'newguest',
				'email': 'newguest@example.com',
				'first_name': 'Nneka',
				'last_name': 'Okafor',
				'phone': '08022222222',
			},
		)

		self.assertEqual(response.status_code, 302)
		guest = UserProfile.objects.get(username='newguest')
		self.assertEqual(guest.role, 'guest')
		self.assertTrue(guest.is_active)
		self.assertTrue(GuestProfile.objects.filter(user=guest).exists())

	def test_staff_creation_from_portal(self):
		self.client.force_login(self.admin)
		response = self.client.post(
			reverse('frontend:portal-staff'),
			data={
				'first_name': 'Amara',
				'last_name': 'Nwosu',
				'email': 'amara@example.com',
				'phone': '08033333333',
				'role': 'receptionist',
				'password': 'secret123',
			},
		)

		self.assertEqual(response.status_code, 302)
		staff = UserProfile.objects.get(email='amara@example.com')
		self.assertEqual(staff.role, 'receptionist')
		self.assertTrue(staff.is_active)

	def test_booking_form_rejects_conflicting_room_dates(self):
		today = timezone.localdate()
		Reservation.objects.create(
			guest=self.guest,
			room=self.room,
			check_in_date=today + timedelta(days=2),
			check_out_date=today + timedelta(days=4),
			num_adults=1,
			nightly_rate=self.room.current_price,
			status='confirmed',
			created_by=self.staff,
		)

		form = BookingRequestForm(
			data={
				'first_name': 'John',
				'last_name': 'Doe',
				'email': 'john@example.com',
				'phone': '08012345678',
				'check_in_date': today + timedelta(days=3),
				'check_out_date': today + timedelta(days=5),
				'room': self.room.id,
				'num_adults': 1,
				'num_children': 0,
				'special_requests': '',
			}
		)
		self.assertFalse(form.is_valid())
		self.assertIn('room', form.errors)

	def test_confirm_action_creates_invoice_and_notification(self):
		today = timezone.localdate()
		reservation = Reservation.objects.create(
			guest=self.guest,
			room=self.room,
			check_in_date=today + timedelta(days=7),
			check_out_date=today + timedelta(days=9),
			num_adults=1,
			nightly_rate=self.room.current_price,
			status='pending',
			created_by=self.staff,
		)

		self.client.force_login(self.staff)
		url = reverse('frontend:portal-reservation-action', args=[reservation.id, 'confirm'])
		response = self.client.post(url)

		self.assertEqual(response.status_code, 302)
		reservation.refresh_from_db()
		self.assertEqual(reservation.status, 'confirmed')

		invoice = Invoice.objects.get(reservation=reservation)
		self.assertEqual(invoice.guest, self.guest)
		self.assertGreater(invoice.total, 0)
		self.assertTrue(invoice.items.exists())

		self.assertTrue(
			Notification.objects.filter(
				recipient=self.guest,
				notification_type='reservation',
				title='Reservation confirmed',
			).exists()
		)
		self.assertTrue(
			AuditLog.objects.filter(
				event_type='reservation',
				action='reservation_confirm',
				target_id=str(reservation.id),
			).exists()
		)

	def test_staff_can_record_completed_payment(self):
		today = timezone.localdate()
		reservation = Reservation.objects.create(
			guest=self.guest,
			room=self.room,
			check_in_date=today + timedelta(days=3),
			check_out_date=today + timedelta(days=5),
			num_adults=1,
			nightly_rate=self.room.current_price,
			status='confirmed',
			created_by=self.staff,
		)
		invoice = Invoice.objects.create(
			reservation=reservation,
			guest=self.guest,
			status='sent',
			due_date=today + timedelta(days=2),
		)
		InvoiceItem.objects.create(
			invoice=invoice,
			description='Accommodation',
			quantity=Decimal('1.00'),
			unit_price=Decimal('20000.00'),
		)
		invoice.save()
		terminal = CashierTerminal.objects.create(code='front-desk', name='Front Desk')
		open_cashier_shift(terminal=terminal, cashier=self.staff, opening_float='5000.00')

		self.client.force_login(self.staff)
		response = self.client.post(
			reverse('frontend:portal-payments'),
			data={
				'invoice': invoice.id,
				'amount': str(invoice.total),
				'method': 'cash',
				'status': 'completed',
				'transaction_id': 'TXN001',
				'notes': 'Paid at front desk',
				'idempotency_key': 'frontend-payment-001',
			},
		)

		self.assertEqual(response.status_code, 302)
		payment = Payment.objects.get(invoice=invoice)
		self.assertEqual(payment.status, 'completed')
		self.assertEqual(payment.processed_by, self.staff)
		self.assertTrue(invoice.receipts.exists())
		self.assertIsNotNone(payment.receipt)
		self.assertEqual(payment.folio.entries.filter(entry_type='payment').count(), 1)
		self.assertEqual(payment.cashier_shift.cash_movements.filter(movement_type='sale').count(), 1)
		self.assertTrue(
			AuditLog.objects.filter(
				event_type='payment',
				action='record_payment',
				target_id=str(payment.id),
			).exists()
		)

	def test_checkout_creates_housekeeping_task(self):
		today = timezone.localdate()
		reservation = Reservation.objects.create(
			guest=self.guest,
			room=self.room,
			check_in_date=today,
			check_out_date=today + timedelta(days=1),
			num_adults=1,
			nightly_rate=self.room.current_price,
			status='confirmed',
			created_by=self.staff,
		)
		self.client.force_login(self.staff)

		check_in_url = reverse('frontend:portal-reservation-action', args=[reservation.id, 'check_in'])
		check_out_url = reverse('frontend:portal-reservation-action', args=[reservation.id, 'check_out'])
		self.client.post(check_in_url)
		self.client.post(check_out_url)

		reservation.refresh_from_db()
		self.room.refresh_from_db()
		self.assertEqual(reservation.status, 'checked_out')
		self.assertEqual(self.room.status, 'housekeeping')
		self.assertTrue(
			HousekeepingTask.objects.filter(
				room=self.room,
				task_type='cleaning',
				status='pending',
			).exists()
		)

	def test_service_order_lifecycle_from_portal(self):
		self.client.force_login(self.staff)
		response = self.client.post(
			reverse('frontend:portal-services'),
			data={
				'guest': self.guest.username,
				'room': self.room.id,
				'menu_item': self.menu_item.id,
				'quantity': 2,
				'notes': 'Room service request',
			},
		)
		self.assertEqual(response.status_code, 302)

		order = ServiceOrder.objects.get(guest=self.guest)
		self.assertGreater(order.total, 0)

		confirm_url = reverse('frontend:portal-service-action', args=[order.id, 'confirm'])
		start_url = reverse('frontend:portal-service-action', args=[order.id, 'start'])
		complete_url = reverse('frontend:portal-service-action', args=[order.id, 'complete'])

		self.client.post(confirm_url)
		self.client.post(start_url)
		self.client.post(complete_url)

		order.refresh_from_db()
		self.assertEqual(order.status, 'completed')
		self.assertTrue(
			AuditLog.objects.filter(
				event_type='service',
				action='service_order_complete',
				target_id=str(order.id),
			).exists()
		)

	def test_guest_cannot_run_staff_service_actions(self):
		order = ServiceOrder.objects.create(guest=self.guest, room=self.room, status='pending', notes='test')
		self.client.force_login(self.guest)
		url = reverse('frontend:portal-service-action', args=[order.id, 'confirm'])
		response = self.client.post(url)
		self.assertEqual(response.status_code, 302)
		order.refresh_from_db()
		self.assertEqual(order.status, 'pending')

	def test_reports_export_endpoints(self):
		self.client.force_login(self.staff)
		csv_response = self.client.get(reverse('frontend:portal-reports-export-csv'))
		self.assertEqual(csv_response.status_code, 200)
		self.assertIn('text/csv', csv_response['Content-Type'])
		self.assertIn('attachment; filename="graceday-inn-report-14d.csv"', csv_response['Content-Disposition'])

		pdf_response = self.client.get(reverse('frontend:portal-reports-export-pdf'))
		self.assertIn(pdf_response.status_code, {200, 501})
		if pdf_response.status_code == 200:
			self.assertIn('application/pdf', pdf_response['Content-Type'])
			self.assertIn('attachment; filename="graceday-inn-report-14d.pdf"', pdf_response['Content-Disposition'])

	def test_reports_respects_days_window_query(self):
		self.client.force_login(self.staff)
		response = self.client.get(reverse('frontend:portal-reports') + '?days=30')
		self.assertEqual(response.status_code, 200)
		self.assertEqual(response.context['selected_days'], 30)
		self.assertEqual(len(json.loads(response.context['trend_labels_json'])), 30)

		csv_response = self.client.get(reverse('frontend:portal-reports-export-csv') + '?days=7')
		self.assertEqual(csv_response.status_code, 200)
		self.assertIn('graceday-inn-report-7d.csv', csv_response['Content-Disposition'])

	def test_public_pages_are_backend_connected(self):
		response_home = self.client.get(reverse('frontend:public-home'))
		self.assertEqual(response_home.status_code, 200)
		self.assertIn('hotel_metrics', response_home.context)
		self.assertIn('featured_menu_items', response_home.context)

		response_about = self.client.get(reverse('frontend:public-about'))
		self.assertEqual(response_about.status_code, 200)
		self.assertIn('about_stats', response_about.context)

		response_offers = self.client.get(reverse('frontend:public-offers'))
		self.assertEqual(response_offers.status_code, 200)
		self.assertContains(response_offers, 'Special Offers')

		response_dining = self.client.get(reverse('frontend:public-dining'))
		self.assertEqual(response_dining.status_code, 200)
		self.assertContains(response_dining, 'Dining at GraceDay Inn')

	def test_reservation_action_permission_matrix(self):
		action_rules = {
			'confirm': {
				'allowed': {'admin', 'manager', 'receptionist'},
				'initial': 'pending',
				'target': 'confirmed',
			},
			'check_in': {
				'allowed': {'admin', 'manager', 'receptionist'},
				'initial': 'confirmed',
				'target': 'checked_in',
			},
			'check_out': {
				'allowed': {'admin', 'manager', 'receptionist'},
				'initial': 'checked_in',
				'target': 'checked_out',
			},
			'cancel': {
				'allowed': {'admin', 'manager', 'receptionist', 'guest'},
				'initial': 'pending',
				'target': 'cancelled',
			},
		}

		today = timezone.localdate()
		case_index = 0
		for action, config in action_rules.items():
			for role, user in self.role_users.items():
				case_index += 1
				start_day = today + timedelta(days=case_index * 5)
				reservation_guest = user if role == 'guest' and action == 'cancel' else self.guest
				reservation = Reservation.objects.create(
					guest=reservation_guest,
					room=self.room,
					check_in_date=start_day,
					check_out_date=start_day + timedelta(days=2),
					num_adults=1,
					nightly_rate=self.room.current_price,
					status=config['initial'],
					created_by=self.staff,
				)
				self.client.force_login(user)
				response = self.client.post(reverse('frontend:portal-reservation-action', args=[reservation.id, action]))
				self.assertEqual(response.status_code, 302)
				reservation.refresh_from_db()
				with self.subTest(action=action, role=role):
					if role in config['allowed']:
						self.assertEqual(reservation.status, config['target'])
					else:
						self.assertEqual(reservation.status, config['initial'])

		other_guest_reservation = Reservation.objects.create(
			guest=self.other_guest,
			room=self.room,
			check_in_date=today + timedelta(days=2),
			check_out_date=today + timedelta(days=4),
			num_adults=1,
			nightly_rate=self.room.current_price,
			status='pending',
			created_by=self.staff,
		)
		self.client.force_login(self.guest)
		response = self.client.post(reverse('frontend:portal-reservation-action', args=[other_guest_reservation.id, 'cancel']))
		self.assertEqual(response.status_code, 302)
		other_guest_reservation.refresh_from_db()
		self.assertEqual(other_guest_reservation.status, 'pending')

	def test_service_action_permission_matrix(self):
		action_rules = {
			'confirm': {'allowed': {'admin', 'manager', 'receptionist'}, 'initial': 'pending', 'target': 'confirmed'},
			'start': {'allowed': {'admin', 'manager', 'receptionist'}, 'initial': 'confirmed', 'target': 'in_progress'},
			'complete': {'allowed': {'admin', 'manager', 'receptionist'}, 'initial': 'in_progress', 'target': 'completed'},
			'cancel': {'allowed': {'admin', 'manager', 'receptionist'}, 'initial': 'pending', 'target': 'cancelled'},
		}

		for action, config in action_rules.items():
			for role, user in self.role_users.items():
				order = ServiceOrder.objects.create(
					guest=self.guest,
					room=self.room,
					status=config['initial'],
					notes='permission matrix service test',
				)
				if action == 'complete':
					ServiceOrderItem.objects.create(order=order, menu_item=self.menu_item, quantity=1)
				self.client.force_login(user)
				response = self.client.post(reverse('frontend:portal-service-action', args=[order.id, action]))
				self.assertEqual(response.status_code, 302)
				order.refresh_from_db()
				with self.subTest(action=action, role=role):
					if role in config['allowed']:
						self.assertEqual(order.status, config['target'])
					else:
						self.assertEqual(order.status, config['initial'])

	def test_housekeeping_action_permission_matrix(self):
		action_rules = {
			'start': {'allowed': {'admin', 'manager', 'receptionist', 'housekeeping'}, 'initial': 'pending', 'target': 'in_progress'},
			'complete': {'allowed': {'admin', 'manager', 'receptionist', 'housekeeping'}, 'initial': 'in_progress', 'target': 'completed'},
			'verify': {'allowed': {'admin', 'manager', 'receptionist'}, 'initial': 'completed', 'target': 'verified'},
		}

		for action, config in action_rules.items():
			for role, user in self.role_users.items():
				task = HousekeepingTask.objects.create(
					room=self.room,
					task_type='cleaning',
					priority='medium',
					status=config['initial'],
					created_by=self.staff,
					completed_at=timezone.now() if config['initial'] == 'completed' else None,
				)
				self.client.force_login(user)
				response = self.client.post(reverse('frontend:portal-housekeeping-action', args=[task.id, action]))
				self.assertEqual(response.status_code, 302)
				task.refresh_from_db()
				with self.subTest(action=action, role=role):
					if role in config['allowed']:
						self.assertEqual(task.status, config['target'])
					else:
						self.assertEqual(task.status, config['initial'])

	def test_maintenance_portal_enforces_downtime_and_management_approval(self):
		self.client.force_login(self.staff)
		response = self.client.post(reverse('frontend:portal-maintenance'), {
			'room': self.room.id, 'title': 'Water leak', 'category': 'plumbing',
			'priority': 'high', 'description': 'Leak below sink',
			'downtime_required': 'on', 'estimated_cost': '5000.00',
		})
		self.assertEqual(response.status_code, 302)
		ticket = MaintenanceTicket.objects.get(room=self.room)
		self.room.refresh_from_db()
		self.assertEqual(self.room.status, 'maintenance')
		self.client.post(reverse('frontend:portal-maintenance-action', args=[ticket.id, 'start']))
		self.client.post(reverse('frontend:portal-maintenance-action', args=[ticket.id, 'resolve']), {
			'notes': 'Pipe replaced', 'actual_cost': '4500.00',
		})
		ticket.refresh_from_db()
		self.assertEqual(ticket.status, 'resolved')
		self.client.force_login(self.guest)
		self.assertEqual(self.client.get(reverse('frontend:portal-maintenance')).status_code, 302)
		self.client.force_login(self.manager)
		self.client.post(reverse('frontend:portal-maintenance-action', args=[ticket.id, 'approve']))
		ticket.refresh_from_db()
		self.assertEqual(ticket.status, 'approved')
		self.assertEqual(ticket.approved_by, self.manager)

	def test_newsletter_subscription(self):
		from apps.frontend.models import NewsletterSubscription
		from apps.notifications.models import ContactPreference
		url = reverse('frontend:subscribe-newsletter')
		response = self.client.post(url, {'email': 'new_subscriber@example.com'})
		self.assertEqual(response.status_code, 302)
		self.assertTrue(NewsletterSubscription.objects.filter(email='new_subscriber@example.com', is_active=True).exists())
		self.assertTrue(ContactPreference.objects.get(email='new_subscriber@example.com').consent_granted)

	@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
	def test_public_contact_creates_traceable_inquiry_case(self):
		from apps.notifications.models import InquiryCase, OutboundMessage
		response = self.client.post(reverse('frontend:public-contact'), {
			'name': 'Public Guest', 'email': 'public-inquiry@example.com',
			'category': 'reservation', 'subject': 'Late arrival',
			'message': 'My flight arrives after midnight.',
		})
		self.assertEqual(response.status_code, 302)
		case = InquiryCase.objects.get(requester_email='public-inquiry@example.com')
		self.assertEqual(case.category, 'reservation')
		self.assertTrue(OutboundMessage.objects.filter(related_id=str(case.id)).exists())

	def test_public_chat_session_is_scoped_and_has_polling_fallback(self):
		from apps.notifications.models import ChatConversation
		start = self.client.post(
			reverse('frontend:chat-start'),
			data=json.dumps({'name': 'Chat Guest', 'email': 'chat@example.com', 'message': '<b>Hello</b>'}),
			content_type='application/json',
		)
		self.assertEqual(start.status_code, 201)
		reference = start.json()['reference']
		conversation = ChatConversation.objects.get(reference=reference)
		self.assertEqual(conversation.messages.get().body, 'Hello')
		poll = self.client.get(reverse('frontend:chat-messages', args=[reference]))
		self.assertEqual(poll.status_code, 200)
		self.assertEqual(len(poll.json()['messages']), 1)
		other_client = self.client_class()
		self.assertEqual(
			other_client.get(reverse('frontend:chat-messages', args=[reference])).status_code, 403
		)

	def test_management_portal_is_role_scoped_and_can_raise_queries(self):
		from apps.frontend.models import ManagementQuery
		self.client.force_login(self.manager)
		response = self.client.get(reverse('frontend:portal-management'))
		self.assertEqual(response.status_code, 200)
		create = self.client.post(reverse('frontend:portal-management'), {
			'title': 'Room revenue check', 'description': 'Validate the daily room revenue.',
			'priority': 'high', 'source_model': 'FolioEntry', 'source_id': '42',
		})
		self.assertEqual(create.status_code, 302)
		self.assertTrue(ManagementQuery.objects.filter(title='Room revenue check').exists())
		self.client.force_login(self.guest)
		self.assertEqual(self.client.get(reverse('frontend:portal-management')).status_code, 302)

	def test_tape_chart_and_reservation_management_are_staff_scoped(self):
		today = timezone.localdate()
		reservation = Reservation.objects.create(
			guest=self.guest, room=self.room, check_in_date=today + timedelta(days=2),
			check_out_date=today + timedelta(days=4), nightly_rate=self.room.current_price,
			status='confirmed', created_by=self.staff,
		)
		self.client.force_login(self.staff)
		chart = self.client.get(reverse('frontend:portal-tape-chart'))
		self.assertEqual(chart.status_code, 200)
		self.assertContains(chart, reservation.reservation_number[-4:])
		manage = self.client.get(reverse('frontend:portal-reservation-manage', args=[reservation.id]))
		self.assertEqual(manage.status_code, 200)
		self.client.force_login(self.guest)
		self.assertEqual(self.client.get(reverse('frontend:portal-tape-chart')).status_code, 302)

	@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
	def test_guest_my_stay_scopes_records_and_creates_linked_requests(self):
		from apps.notifications.models import InquiryCase
		today = timezone.localdate()
		own = Reservation.objects.create(
			guest=self.guest, room=self.room, check_in_date=today + timedelta(days=2),
			check_out_date=today + timedelta(days=4), nightly_rate=self.room.current_price,
			status='confirmed', created_by=self.staff,
		)
		other_room = Room.objects.create(number='202', room_type=self.room_type)
		other = Reservation.objects.create(
			guest=self.other_guest, room=other_room, check_in_date=today + timedelta(days=5),
			check_out_date=today + timedelta(days=6), nightly_rate=other_room.current_price,
			status='confirmed', created_by=self.staff,
		)
		self.client.force_login(self.guest)
		response = self.client.get(reverse('frontend:portal-my-stay'))
		self.assertEqual(response.status_code, 200)
		self.assertContains(response, own.reservation_number)
		self.assertNotContains(response, other.reservation_number)
		request_response = self.client.post(reverse('frontend:portal-my-stay'), {
			'reservation': own.id, 'request_type': 'change',
			'message': 'Please extend my stay by one night.',
		})
		self.assertEqual(request_response.status_code, 302)
		case = InquiryCase.objects.get(requester=self.guest)
		self.assertEqual(case.reservation, own)
		self.client.force_login(self.staff)
		self.assertEqual(self.client.get(reverse('frontend:portal-my-stay')).status_code, 302)

	@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
	def test_ready_newsletter_uses_logged_outbox_and_suppression(self):
		from apps.frontend.models import NewsletterMessage, NewsletterSubscription
		from apps.notifications.models import OutboundMessage, Suppression
		NewsletterSubscription.objects.create(email='active-reader@example.com')
		NewsletterSubscription.objects.create(email='suppressed-reader@example.com')
		Suppression.objects.create(email='suppressed-reader@example.com', reason='unsubscribe')
		newsletter = NewsletterMessage.objects.create(
			subject='August at GraceDay', title='A restful August', message='New offers',
			status='ready_to_send',
		)
		self.client.force_login(self.manager)
		response = self.client.post(reverse('frontend:portal-newsletter-send', args=[newsletter.id]))
		self.assertEqual(response.status_code, 302)
		newsletter.refresh_from_db()
		self.assertEqual(newsletter.status, 'sent')
		self.assertEqual(newsletter.recipient_count, 1)
		self.assertEqual(OutboundMessage.objects.filter(related_id=str(newsletter.id)).count(), 1)

	def test_housekeeper_cannot_access_financial_or_service_portals(self):
		self.client.force_login(self.housekeeper)
		for route in (
			'frontend:portal-billing',
			'frontend:portal-payments',
			'frontend:portal-services',
		):
			with self.subTest(route=route):
				response = self.client.get(reverse(route))
				self.assertEqual(response.status_code, 302)

	def test_front_desk_today_board_scopes_operational_roles(self):
		today = timezone.localdate()
		reservation = Reservation.objects.create(
			guest=self.guest, room=self.room, check_in_date=today,
			check_out_date=today + timedelta(days=1), nightly_rate=self.room.current_price,
			status='confirmed', created_by=self.staff,
		)
		self.client.force_login(self.staff)
		response = self.client.get(reverse('frontend:portal-front-desk'))
		self.assertEqual(response.status_code, 200)
		self.assertIn(reservation, response.context['arrivals'])
		self.client.force_login(self.guest)
		self.assertEqual(self.client.get(reverse('frontend:portal-front-desk')).status_code, 302)

	def test_front_desk_search_and_keyboard_accessibility_contract(self):
		today = timezone.localdate()
		matching = Reservation.objects.create(
			guest=self.guest, room=self.room, check_in_date=today,
			check_out_date=today + timedelta(days=1), nightly_rate=self.room.current_price,
			status='confirmed', created_by=self.staff,
		)
		other_guest = UserProfile.objects.create_user(
			'other-today-guest', password='pass', role='guest', first_name='Unmatched',
		)
		Reservation.objects.create(
			guest=other_guest, room=self.room, check_in_date=today,
			check_out_date=today + timedelta(days=1), nightly_rate=self.room.current_price,
			status='confirmed', created_by=self.staff,
		)
		self.client.force_login(self.staff)
		response = self.client.get(reverse('frontend:portal-front-desk'), {'q': self.guest.username})
		self.assertEqual(response.status_code, 200)
		self.assertEqual(list(response.context['arrivals']), [matching])
		self.assertContains(response, 'id="front-desk-search"')
		self.assertContains(response, 'for="front-desk-search"')
		self.assertContains(response, 'id="portal-main-content"')
		self.assertContains(response, 'Skip to main content')
		self.assertContains(response, "event.altKey && event.key.toLowerCase() === 'n'")
		self.assertContains(response, 'scope="col"')

	def test_guest_room_detail_does_not_expose_other_guest_reservations(self):
		today = timezone.localdate()
		Reservation.objects.create(
			guest=self.other_guest,
			room=self.room,
			check_in_date=today + timedelta(days=20),
			check_out_date=today + timedelta(days=22),
			nightly_rate=self.room.current_price,
		)
		self.client.force_login(self.guest)
		response = self.client.get(reverse('frontend:portal-room-detail', args=[self.room.id]))
		self.assertEqual(response.status_code, 200)
		self.assertEqual(list(response.context['recent_reservations']), [])

	def test_manager_can_view_but_cannot_create_or_mutate_staff(self):
		self.client.force_login(self.manager)
		view_response = self.client.get(reverse('frontend:portal-staff'))
		self.assertEqual(view_response.status_code, 200)
		self.assertFalse(view_response.context['can_manage_staff'])

		create_response = self.client.post(reverse('frontend:portal-staff'), {
			'first_name': 'Unauthorized', 'last_name': 'Admin',
			'email': 'unauthorized@example.com', 'role': 'admin',
		})
		self.assertEqual(create_response.status_code, 302)
		self.assertFalse(UserProfile.objects.filter(email='unauthorized@example.com').exists())

		action_response = self.client.post(
			reverse('frontend:portal-staff-action', args=[self.admin.id, 'deactivate'])
		)
		self.assertEqual(action_response.status_code, 302)
		self.admin.refresh_from_db()
		self.assertTrue(self.admin.is_active)

	def _public_booking_payload(self, email='otp-guest@example.com'):
		today = timezone.localdate()
		return {
			'first_name': 'OTP', 'last_name': 'Guest', 'email': email,
			'phone': '08012340000', 'check_in_date': today + timedelta(days=40),
			'check_out_date': today + timedelta(days=42), 'room': self.room.id,
			'num_adults': 1, 'num_children': 0, 'special_requests': '',
		}

	def _start_public_verification(self, email='otp-guest@example.com'):
		quote_response = self.client.post(
			reverse('frontend:public-room-detail', args=[self.room.id]), self._public_booking_payload(email=email)
		)
		self.assertRedirects(
			quote_response, reverse('frontend:public-quote-confirm'), fetch_redirect_response=False
		)
		return self.client.post(reverse('frontend:public-quote-confirm'))

	@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
	def test_booking_otp_is_hashed_expires_and_clears_after_success(self):
		response = self._start_public_verification()
		self.assertRedirects(response, reverse('frontend:portal-verify-booking'), fetch_redirect_response=False)
		session = self.client.session
		self.assertIn('booking_verify_hash', session)
		self.assertNotIn('booking_verify_code', session)
		code = re.search(r'verification code is:\s*(\d{6})', mail.outbox[0].body, re.IGNORECASE).group(1)

		verify_response = self.client.post(
			reverse('frontend:portal-verify-booking'), {'verification_code': code}
		)
		self.assertEqual(verify_response.status_code, 302)
		verified_reservation = Reservation.objects.get(guest__email='otp-guest@example.com')
		self.assertEqual(verified_reservation.source_quote.status, 'converted')
		self.assertEqual(verified_reservation.source, 'direct_website')
		self.assertEqual(verified_reservation.price_snapshot['currency'], 'NGN')
		self.assertNotIn('booking_verify_hash', self.client.session)
		created_user = UserProfile.objects.get(email='otp-guest@example.com')
		self.assertFalse(created_user.has_usable_password())
		self.assertNotIn('Password:', mail.outbox[1].body)

		html_email = mail.outbox[1].alternatives[0][0]
		setup_path = re.search(r'href="http://testserver([^"]+/set-password/[^"]+)"', html_email)
		if setup_path is None:
			setup_path = re.search(r'href="http://testserver([^"]*set-password[^"]+)"', html_email)
		self.assertIsNotNone(setup_path)
		setup_url = setup_path.group(1)
		password_response = self.client.post(setup_url, {
			'new_password1': 'Secure-booking-pass-2026',
			'new_password2': 'Secure-booking-pass-2026',
		})
		self.assertRedirects(password_response, reverse('frontend:portal-dashboard'), fetch_redirect_response=False)
		created_user.refresh_from_db()
		self.assertTrue(created_user.check_password('Secure-booking-pass-2026'))
		self.assertEqual(self.client.get(setup_url).status_code, 400)

	@override_settings(
		EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
		BOOKING_OTP_MAX_ATTEMPTS=2,
	)
	def test_booking_otp_locks_after_maximum_attempts(self):
		self._start_public_verification()
		url = reverse('frontend:portal-verify-booking')
		self.client.post(url, {'verification_code': '000000'})
		response = self.client.post(url, {'verification_code': '111111'})
		self.assertRedirects(response, reverse('frontend:public-home'), fetch_redirect_response=False)
		self.assertNotIn('booking_verify_hash', self.client.session)
		self.assertFalse(Reservation.objects.filter(guest__email='otp-guest@example.com').exists())

	@override_settings(EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend')
	def test_expired_booking_otp_is_rejected(self):
		self._start_public_verification()
		session = self.client.session
		session['booking_verify_expires_at'] = 0
		session.save()
		response = self.client.post(
			reverse('frontend:portal-verify-booking'), {'verification_code': '000000'}
		)
		self.assertRedirects(response, reverse('frontend:public-home'), fetch_redirect_response=False)
		self.assertNotIn('booking_verify_hash', self.client.session)

	@override_settings(
		EMAIL_BACKEND='django.core.mail.backends.locmem.EmailBackend',
		BOOKING_OTP_SEND_LIMIT=1,
	)
	def test_booking_otp_send_is_rate_limited(self):
		url = reverse('frontend:public-home')
		self._start_public_verification()
		
		# Use different dates so we don't get validation error about room availability
		payload = self._public_booking_payload(email='second-otp@example.com')
		today = timezone.localdate()
		payload['check_in_date'] = today + timedelta(days=45)
		payload['check_out_date'] = today + timedelta(days=47)
		
		quote_response = self.client.post(
			reverse('frontend:public-room-detail', args=[self.room.id]),
			payload
		)
		self.assertRedirects(quote_response, reverse('frontend:public-quote-confirm'), fetch_redirect_response=False)
		
		response = self.client.post(reverse('frontend:public-quote-confirm'))
		self.assertRedirects(response, url, fetch_redirect_response=False)
		self.assertEqual(len(mail.outbox), 1)

	@override_settings(LOGIN_FAILURE_LIMIT=2, LOGIN_FAILURE_WINDOW_SECONDS=900)
	def test_portal_login_is_throttled_and_audited(self):
		url = reverse('frontend:portal-sign-in')
		self.client.post(url, {'username': self.guest.username, 'password': 'wrong-one'})
		self.client.post(url, {'username': self.guest.username, 'password': 'wrong-two'})
		blocked = self.client.post(url, {
			'username': self.guest.username, 'password': self.test_secret,
		})
		self.assertEqual(blocked.status_code, 200)
		self.assertNotIn('_auth_user_id', self.client.session)
		self.assertEqual(
			AuditLog.objects.filter(action='portal_login_failed').count(), 2
		)
		self.assertTrue(AuditLog.objects.filter(action='portal_login_blocked').exists())
