from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import UserProfile
from apps.rooms.models import Promotion, Room, RoomType

from .models import CorporateAccount, GroupBooking
from .pricing import convert_quote, create_quote
from .services import transition_reservation


class CommercialReservationTests(TestCase):
    def setUp(self):
        self.manager = UserProfile.objects.create_user(
            username='commercial-manager', email='commercial-manager@example.com',
            password='Strong-test-password-2026', role='manager',
        )
        self.guest = UserProfile.objects.create_user(
            username='commercial-guest', email='commercial-guest@example.com',
            password='Strong-test-password-2026', role='guest',
        )
        self.receptionist = UserProfile.objects.create_user(
            username='commercial-reception', email='commercial-reception@example.com',
            password='Strong-test-password-2026', role='receptionist',
        )
        self.room_type = RoomType.objects.create(name='Commercial King', base_price='10000.00', max_occupancy=2)
        self.room = Room.objects.create(number='COM-1', room_type=self.room_type)
        self.plan = self.room_type.rate_plans.get()

    def test_promotion_is_snapshotted_and_counted_once_on_conversion(self):
        promotion = Promotion.objects.create(
            code='stay20', name='Stay 20', discount_type='percentage', amount='20.00',
            valid_from=timezone.now() - timedelta(days=1),
            valid_to=timezone.now() + timedelta(days=10), usage_limit=1,
        )
        promotion.room_types.add(self.room_type)
        arrival = timezone.localdate() + timedelta(days=10)
        quote = create_quote(
            room=self.room, rate_plan=self.plan, check_in_date=arrival,
            check_out_date=arrival + timedelta(days=2), guest=self.guest,
            promotion_code='STAY20',
        )
        self.assertEqual(quote.discount_total, Decimal('4000.00'))
        self.assertEqual(quote.price_snapshot['subtotal_before_discount'], '20000.00')
        self.assertEqual(quote.price_snapshot['subtotal'], '16000.00')
        reservation = convert_quote(quote_id=quote.id, guest=self.guest, created_by=self.manager)
        promotion.refresh_from_db()
        self.assertEqual(promotion.times_used, 1)
        self.assertEqual(reservation.price_snapshot['promotion_code'], 'stay20')

    def test_late_cancellation_reverses_stay_and_posts_snapshotted_fee(self):
        self.plan.free_cancellation_hours = 48
        self.plan.cancellation_fee_percent = Decimal('50.00')
        self.plan.save()
        arrival = timezone.localdate() + timedelta(days=1)
        quote = create_quote(
            room=self.room, rate_plan=self.plan, check_in_date=arrival,
            check_out_date=arrival + timedelta(days=2), guest=self.guest,
        )
        reservation = convert_quote(quote_id=quote.id, guest=self.guest, created_by=self.manager)
        reservation = transition_reservation(reservation_id=reservation.id, action='cancel', actor=self.manager)
        self.assertEqual(reservation.cancellation_fee, Decimal('10000.00'))
        self.assertEqual(reservation.folio.balance, Decimal('10000.00'))
        history = reservation.status_history.last()
        self.assertEqual(history.metadata['fee_percent'], '50.00')

    def test_staff_can_manage_corporate_groups_and_link_reservations(self):
        account = CorporateAccount.objects.create(
            name='Example Industries', account_code='example-industries',
            billing_email='accounts@example-industries.test', credit_limit='500000.00',
        )
        client = APIClient()
        client.force_authenticate(self.manager)
        arrival = timezone.localdate() + timedelta(days=20)
        response = client.post('/api/group-bookings/', {
            'name': 'Leadership Retreat', 'corporate_account': account.id,
            'arrival_date': arrival, 'departure_date': arrival + timedelta(days=2),
            'room_target': 5, 'status': 'open',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        group = GroupBooking.objects.get()
        from .services import create_reservation
        reservation = create_reservation(
            guest=self.guest, room=self.room, check_in_date=arrival,
            check_out_date=arrival + timedelta(days=2), created_by=self.manager,
            source='front_desk', corporate_account=account, group_booking=group,
        )
        self.assertEqual(reservation.group_booking, group)
        self.assertEqual(group.reservations.count(), 1)

    def test_discount_requires_separate_manager_approval_and_posts_credit(self):
        arrival = timezone.localdate() + timedelta(days=15)
        quote = create_quote(
            room=self.room, rate_plan=self.plan, check_in_date=arrival,
            check_out_date=arrival + timedelta(days=2), guest=self.guest,
        )
        reservation = convert_quote(quote_id=quote.id, guest=self.guest, created_by=self.receptionist)
        from .services import request_reservation_discount, review_reservation_discount
        discount = request_reservation_discount(
            reservation_id=reservation.id, amount='2000.00',
            reason='Approved service recovery', actor=self.receptionist,
        )
        reviewed = review_reservation_discount(
            request_id=discount.id, action='approve', actor=self.manager, note='Within delegated limit',
        )
        self.assertEqual(reviewed.status, 'approved')
        self.assertEqual(reservation.folio.balance, Decimal('18000.00'))
        self.assertTrue(reservation.folio.entries.filter(
            external_key=f'reservation-discount:{discount.id}', entry_type='credit_note'
        ).exists())

    def test_commercial_portal_exposes_role_scoped_account_and_group_workflows(self):
        self.client.force_login(self.manager)
        page = self.client.get(reverse('frontend:portal-commercial'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Corporate, groups')
        response = self.client.post(reverse('frontend:portal-commercial'), {
            'command': 'corporate_create', 'name': 'Portal Company',
            'account_code': 'portal-company', 'billing_email': 'billing@portal.test',
            'credit_limit': '100000', 'payment_terms_days': '30',
        })
        self.assertRedirects(response, reverse('frontend:portal-commercial'), fetch_redirect_response=False)
        self.assertTrue(CorporateAccount.objects.filter(account_code='portal-company').exists())

        self.client.force_login(self.receptionist)
        forbidden_create = self.client.post(reverse('frontend:portal-commercial'), {
            'command': 'corporate_create', 'name': 'Unauthorized Company',
            'account_code': 'unauthorized-company', 'billing_email': 'no@portal.test',
        })
        self.assertRedirects(forbidden_create, reverse('frontend:portal-commercial'), fetch_redirect_response=False)
        self.assertFalse(CorporateAccount.objects.filter(account_code='unauthorized-company').exists())
