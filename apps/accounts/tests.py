from datetime import timedelta
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from django.test import RequestFactory
from django.test import override_settings
from django.core.cache import cache
from django.contrib import admin
from rest_framework import status
from rest_framework.test import APITestCase

from apps.billing.models import Invoice
from apps.housekeeping.models import HousekeepingTask
from apps.payments.models import Payment
from apps.reservations.models import BookingQuote, Reservation
from apps.rooms.models import RatePlan, Room, RoomType
from apps.services.models import MenuItem, ServiceCategory, ServiceOrder, ServiceOrderItem
from apps.frontend.models import AuditLog

from .models import UserProfile
from .admin import UserProfileAdmin


class ApiAuthorizationTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.admin = UserProfile.objects.create_user('admin-api', password='test-pass', role='admin')
        self.manager = UserProfile.objects.create_user('manager-api', password='test-pass', role='manager')
        self.guest = UserProfile.objects.create_user('guest-api', password='test-pass', role='guest')
        self.other_guest = UserProfile.objects.create_user('other-api', password='test-pass', role='guest')
        self.housekeeper = UserProfile.objects.create_user(
            'housekeeper-api', password='test-pass', role='housekeeping'
        )
        room_type = RoomType.objects.create(
            name='API Deluxe', base_price=Decimal('25000.00'), max_occupancy=2
        )
        self.room = Room.objects.create(number='API-1', room_type=room_type)
        self.rate_plan = RatePlan.objects.create(
            room_type=room_type, name='API Flexible', code='api-flexible',
            deposit_percent=Decimal('25.00'),
        )
        today = timezone.localdate()
        self.own_reservation = Reservation.objects.create(
            guest=self.guest, room=self.room, check_in_date=today + timedelta(days=1),
            check_out_date=today + timedelta(days=2), nightly_rate=room_type.base_price,
        )
        self.other_reservation = Reservation.objects.create(
            guest=self.other_guest, room=self.room, check_in_date=today + timedelta(days=3),
            check_out_date=today + timedelta(days=4), nightly_rate=room_type.base_price,
        )
        self.own_invoice = Invoice.objects.create(
            reservation=self.own_reservation, guest=self.guest
        )
        self.other_invoice = Invoice.objects.create(
            reservation=self.other_reservation, guest=self.other_guest
        )
        Payment.objects.create(invoice=self.own_invoice, amount=Decimal('1000.00'))
        Payment.objects.create(invoice=self.other_invoice, amount=Decimal('1000.00'))

    def test_public_registration_cannot_assign_privileged_role(self):
        response = self.client.post(reverse('api-register'), {
            'username': 'attacker', 'email': 'attacker@example.com',
            'password': 'strong-pass-123', 'password_confirm': 'strong-pass-123',
            'role': 'admin',
        })
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(UserProfile.objects.filter(username='attacker').exists())

    def test_public_registration_creates_guest_account(self):
        response = self.client.post(reverse('api-register'), {
            'username': 'new-guest', 'email': 'new-guest@example.com',
            'password': 'strong-pass-123', 'password_confirm': 'strong-pass-123',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(UserProfile.objects.get(username='new-guest').role, 'guest')

    def test_guest_cannot_list_users_or_promote_self(self):
        self.client.force_authenticate(self.guest)
        self.assertEqual(self.client.get('/api/users/').status_code, status.HTTP_403_FORBIDDEN)
        response = self.client.patch(reverse('api-me'), {'role': 'admin'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.guest.refresh_from_db()
        self.assertEqual(self.guest.role, 'guest')

    def test_manager_can_read_users_but_cannot_modify_them(self):
        self.client.force_authenticate(self.manager)
        self.assertEqual(self.client.get('/api/users/').status_code, status.HTTP_200_OK)
        response = self.client.patch(f'/api/users/{self.guest.pk}/', {'first_name': 'Changed'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_guest_only_sees_own_reservations_finances_and_payments(self):
        self.client.force_authenticate(self.guest)
        reservations = self.client.get('/api/reservations/').data['results']
        invoices = self.client.get('/api/invoices/').data['results']
        payments = self.client.get('/api/payments/').data['results']
        self.assertEqual({item['id'] for item in reservations}, {self.own_reservation.id})
        self.assertEqual({item['id'] for item in invoices}, {self.own_invoice.id})
        self.assertEqual({item['invoice'] for item in payments}, {self.own_invoice.id})
        self.assertEqual(
            self.client.get(f'/api/reservations/{self.other_reservation.pk}/').status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_guest_reservation_creation_forces_ownership_and_pending_status(self):
        self.client.force_authenticate(self.guest)
        today = timezone.localdate()
        response = self.client.post('/api/reservations/', {
            'guest': self.other_guest.id,
            'room': self.room.id,
            'check_in_date': today + timedelta(days=10),
            'check_out_date': today + timedelta(days=12),
            'num_adults': 1,
        }, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        reservation = Reservation.objects.get(pk=response.data['id'])
        self.assertEqual(reservation.guest, self.guest)
        self.assertEqual(reservation.status, 'pending')
        self.assertEqual(reservation.source, 'api')
        self.assertEqual(response.data['status_history'][0]['action'], 'create')
        self.assertEqual(response.data['room_assignments'][0]['room'], self.room.id)
        self.assertTrue(AuditLog.objects.filter(
            actor=self.guest, action='api_create', target_model='Reservation',
            target_id=str(reservation.id),
        ).exists())

    def test_generic_reservation_update_and_delete_are_disabled(self):
        self.client.force_authenticate(self.admin)
        patch_response = self.client.patch(
            f'/api/reservations/{self.own_reservation.id}/', {'status': 'checked_in'}
        )
        delete_response = self.client.delete(
            f'/api/reservations/{self.own_reservation.id}/'
        )
        self.assertEqual(patch_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(delete_response.status_code, status.HTTP_403_FORBIDDEN)
        self.own_reservation.refresh_from_db()
        self.assertEqual(self.own_reservation.status, 'pending')

    def test_financial_document_resources_are_read_only_for_every_role(self):
        for user in (self.admin, self.manager, self.guest):
            with self.subTest(role=user.role):
                self.client.force_authenticate(user)
                self.assertIn(
                    self.client.post('/api/invoices/', {
                        'reservation': self.own_reservation.id, 'guest': self.guest.id,
                    }).status_code,
                    {status.HTTP_403_FORBIDDEN, status.HTTP_405_METHOD_NOT_ALLOWED},
                )
                self.assertIn(
                    self.client.patch(
                        f'/api/invoices/{self.own_invoice.id}/', {'status': 'paid'}, format='json'
                    ).status_code,
                    {status.HTTP_403_FORBIDDEN, status.HTTP_405_METHOD_NOT_ALLOWED},
                )
                self.assertIn(
                    self.client.delete(f'/api/invoices/{self.own_invoice.id}/').status_code,
                    {status.HTTP_403_FORBIDDEN, status.HTTP_405_METHOD_NOT_ALLOWED},
                )
                self.assertIn(
                    self.client.post('/api/invoice-items/', {
                        'invoice': self.own_invoice.id, 'description': 'Injected',
                        'quantity': 1, 'unit_price': '1.00',
                    }).status_code,
                    {status.HTTP_403_FORBIDDEN, status.HTTP_405_METHOD_NOT_ALLOWED},
                )
                self.assertIn(
                    self.client.post('/api/receipts/', {
                        'invoice': self.own_invoice.id, 'amount': '1.00',
                    }).status_code,
                    {status.HTTP_403_FORBIDDEN, status.HTTP_405_METHOD_NOT_ALLOWED},
                )

    def test_service_items_change_only_through_scoped_pending_order_commands(self):
        category = ServiceCategory.objects.create(name='API Dining')
        menu_item = MenuItem.objects.create(
            category=category, name='Breakfast', price=Decimal('5000.00'), is_available=True,
        )
        own_order = ServiceOrder.objects.create(guest=self.guest, room=self.room)
        other_order = ServiceOrder.objects.create(guest=self.other_guest, room=self.room)
        self.client.force_authenticate(self.guest)

        self.assertIn(
            self.client.post('/api/service-order-items/', {
                'order': own_order.id, 'menu_item': menu_item.id, 'quantity': 1,
            }).status_code,
            {status.HTTP_403_FORBIDDEN, status.HTTP_405_METHOD_NOT_ALLOWED},
        )
        added = self.client.post(
            f'/api/service-orders/{own_order.id}/items/',
            {'menu_item': menu_item.id, 'quantity': 2}, format='json',
        )
        self.assertEqual(added.status_code, status.HTTP_201_CREATED)
        item = ServiceOrderItem.objects.get(order=own_order)
        self.assertEqual(item.subtotal, Decimal('10000.00'))
        self.assertEqual(
            self.client.post(
                f'/api/service-orders/{other_order.id}/items/',
                {'menu_item': menu_item.id, 'quantity': 1}, format='json',
            ).status_code,
            status.HTTP_404_NOT_FOUND,
        )
        own_order.status = 'confirmed'
        own_order.save(update_fields=['status'])
        blocked = self.client.post(
            f'/api/service-orders/{own_order.id}/items/{item.id}/remove/', {}, format='json',
        )
        self.assertEqual(blocked.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertTrue(ServiceOrderItem.objects.filter(pk=item.id).exists())

    def test_guest_can_create_and_convert_own_quote(self):
        self.client.force_authenticate(self.guest)
        today = timezone.localdate()
        create_response = self.client.post('/api/booking-quotes/', {
            'room': self.room.id,
            'rate_plan': self.rate_plan.id,
            'check_in_date': today + timedelta(days=20),
            'check_out_date': today + timedelta(days=22),
            'num_adults': 1,
            'num_children': 0,
            'guest': self.other_guest.id,
        }, format='json')
        self.assertEqual(create_response.status_code, status.HTTP_201_CREATED)
        quote = BookingQuote.objects.get(pk=create_response.data['id'])
        self.assertEqual(quote.guest, self.guest)
        self.assertEqual(quote.price_snapshot['deposit_required'], '12500.00')

        convert_response = self.client.post(
            f'/api/booking-quotes/{quote.id}/convert/', {}, format='json'
        )
        self.assertEqual(convert_response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(convert_response.data['guest'], self.guest.id)

    def test_guest_cannot_mutate_room_or_create_notification(self):
        self.room.notes = 'Internal maintenance observation'
        self.room.save(update_fields=['notes'])
        self.client.force_authenticate(self.guest)
        guest_room = self.client.get(f'/api/rooms/{self.room.id}/')
        self.assertNotIn('notes', guest_room.data)
        room_response = self.client.post('/api/rooms/', {
            'number': 'API-2', 'room_type': self.room.room_type_id, 'floor': 1,
        })
        notification_response = self.client.post('/api/notifications/', {
            'recipient': self.other_guest.id, 'title': 'spam', 'message': 'spam',
        })
        self.assertEqual(room_response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(notification_response.status_code, status.HTTP_403_FORBIDDEN)
        self.client.force_authenticate(self.admin)
        self.assertEqual(
            self.client.get(f'/api/rooms/{self.room.id}/').data['notes'],
            'Internal maintenance observation',
        )

    def test_housekeeper_only_sees_assigned_tasks(self):
        assigned = HousekeepingTask.objects.create(room=self.room, assigned_to=self.housekeeper)
        HousekeepingTask.objects.create(room=self.room, assigned_to=None)
        self.client.force_authenticate(self.housekeeper)
        response = self.client.get('/api/housekeeping-tasks/')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual({item['id'] for item in response.data['results']}, {assigned.id})

    def test_django_admin_is_read_only_for_manager_and_hidden_from_housekeeping(self):
        model_admin = UserProfileAdmin(UserProfile, admin.site)
        factory = RequestFactory()

        self.manager.is_staff = True
        self.manager.save(update_fields=['is_staff'])
        manager_request = factory.get('/admin/accounts/userprofile/')
        manager_request.user = self.manager
        self.assertTrue(model_admin.has_view_permission(manager_request))
        self.assertFalse(model_admin.has_change_permission(manager_request))

        self.housekeeper.is_staff = True
        self.housekeeper.save(update_fields=['is_staff'])
        housekeeper_request = factory.get('/admin/accounts/userprofile/')
        housekeeper_request.user = self.housekeeper
        self.assertFalse(model_admin.has_module_permission(housekeeper_request))

        self.admin.is_staff = True
        self.admin.save(update_fields=['is_staff'])
        admin_request = factory.get('/admin/accounts/userprofile/')
        admin_request.user = self.admin
        self.assertTrue(model_admin.has_change_permission(admin_request))

    @override_settings(LOGIN_FAILURE_LIMIT=2, LOGIN_FAILURE_WINDOW_SECONDS=900)
    def test_api_login_is_throttled_and_audited(self):
        url = reverse('api-login')
        self.client.post(url, {'username': self.guest.username, 'password': 'wrong-one'})
        self.client.post(url, {'username': self.guest.username, 'password': 'wrong-two'})
        blocked = self.client.post(url, {
            'username': self.guest.username, 'password': 'test-pass',
        })
        self.assertEqual(blocked.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(AuditLog.objects.filter(action='api_login_failed').count(), 2)
        self.assertTrue(AuditLog.objects.filter(action='api_login_blocked').exists())
