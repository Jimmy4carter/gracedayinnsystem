import json
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.billing.models import Invoice, InvoiceItem
from apps.housekeeping.models import HousekeepingTask
from apps.notifications.models import Notification
from apps.payments.models import Payment
from apps.reservations.models import Reservation
from apps.rooms.models import Room, RoomType
from apps.services.models import MenuItem, ServiceCategory, ServiceOrder

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
			},
		)

		self.assertEqual(response.status_code, 302)
		payment = Payment.objects.get(invoice=invoice)
		self.assertEqual(payment.status, 'completed')
		self.assertEqual(payment.processed_by, self.staff)
		self.assertTrue(invoice.receipts.exists())
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
				'guest': self.guest.id,
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
		self.assertContains(response_dining, 'Dining at GRACEDAY INN')

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
			'complete': {'allowed': {'admin', 'manager', 'receptionist', 'housekeeping'}, 'initial': 'pending', 'target': 'completed'},
			'verify': {'allowed': {'admin', 'manager', 'receptionist', 'housekeeping'}, 'initial': 'completed', 'target': 'verified'},
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

	def test_newsletter_subscription(self):
		from apps.frontend.models import NewsletterSubscription
		url = reverse('frontend:subscribe-newsletter')
		response = self.client.post(url, {'email': 'new_subscriber@example.com'})
		self.assertEqual(response.status_code, 302)
		self.assertTrue(NewsletterSubscription.objects.filter(email='new_subscriber@example.com', is_active=True).exists())
