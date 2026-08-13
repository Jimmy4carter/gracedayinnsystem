import re
from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.billing.models import Invoice
from apps.housekeeping.models import HousekeepingTask
from apps.rooms.models import DailyRate, RatePlan, Room, RoomType, TaxFee

from .models import BookingQuote, InventoryHold, Reservation, WaitlistEntry
from .pricing import calculate_quote, convert_quote, create_quote, expire_stale_holds
from .services import (
    ReservationConflict, amend_reservation_stay, create_reservation,
    convert_waitlist_entry, move_reservation_room, offer_waitlist_entry,
    transition_reservation,
)


class ReservationCommandTests(TestCase):
    def setUp(self):
        self.staff = UserProfile.objects.create_user('reservation-staff', role='receptionist')
        self.guest = UserProfile.objects.create_user('reservation-guest', role='guest')
        self.other_guest = UserProfile.objects.create_user('reservation-guest-2', role='guest')
        self.room_type = RoomType.objects.create(
            name='Command Suite', base_price=Decimal('30000.00'), max_occupancy=2
        )
        self.room = Room.objects.create(number='CMD-1', room_type=self.room_type)
        self.rate_plan = RatePlan.objects.create(
            room_type=self.room_type, name='Flexible', code='flexible',
            deposit_percent=Decimal('50.00'), min_stay=1, max_stay=14,
            cancellation_policy='Cancel by 18:00 one day before arrival.',
        )
        self.today = timezone.localdate()

    def _create(self, guest=None, start=2, end=4, **kwargs):
        return create_reservation(
            guest=guest or self.guest,
            room=self.room,
            check_in_date=self.today + timedelta(days=start),
            check_out_date=self.today + timedelta(days=end),
            created_by=self.staff,
            **kwargs,
        )

    def test_pending_reservation_blocks_overlapping_inventory(self):
        self._create()
        with self.assertRaises(ReservationConflict):
            self._create(guest=self.other_guest, start=3, end=5)
        adjacent = self._create(guest=self.other_guest, start=4, end=6)
        self.assertEqual(adjacent.status, 'pending')

    def test_command_enforces_dates_occupancy_and_sellable_inventory(self):
        with self.assertRaises(ValidationError):
            self._create(start=-2, end=1)
        with self.assertRaises(ValidationError):
            self._create(start=3, end=3)
        with self.assertRaises(ValidationError):
            self._create(start=7, end=8, num_adults=2, num_children=1)
        self.room.status = 'maintenance'
        self.room.save(update_fields=['status'])
        reservation = self._create(start=9, end=10)
        self.assertEqual(reservation.status, 'pending')
        self.room.is_sellable = False
        self.room.save(update_fields=['is_sellable'])
        with self.assertRaises(ValidationError):
            self._create(start=11, end=12)

    def test_transition_state_machine_creates_operational_side_effects(self):
        reservation = self._create(start=0, end=1)
        self.assertEqual(reservation.source, 'admin')
        self.assertEqual(reservation.price_snapshot['currency'], 'NGN')
        self.assertEqual(reservation.price_snapshot['nightly_rate'], '30000.00')
        self.assertEqual(reservation.status_history.count(), 1)
        self.assertEqual(reservation.room_assignments.count(), 1)
        reservation = transition_reservation(
            reservation_id=reservation.id, action='confirm', actor=self.staff
        )
        self.assertEqual(reservation.status, 'confirmed')
        self.assertTrue(Invoice.objects.filter(reservation=reservation).exists())

        reservation = transition_reservation(
            reservation_id=reservation.id, action='check_in', actor=self.staff
        )
        self.assertEqual(reservation.status, 'checked_in')
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, 'occupied')

        reservation = transition_reservation(
            reservation_id=reservation.id, action='check_out', actor=self.staff
        )
        self.assertEqual(reservation.status, 'checked_out')
        self.assertEqual(
            list(reservation.status_history.values_list('action', flat=True)),
            ['create', 'confirm', 'check_in', 'check_out'],
        )
        self.assertIsNotNone(reservation.room_assignments.get().released_at)
        self.assertTrue(HousekeepingTask.objects.filter(
            room=self.room, status='pending', task_type='cleaning'
        ).exists())

        with self.assertRaises(ValidationError):
            transition_reservation(
                reservation_id=reservation.id, action='confirm', actor=self.staff
            )

    def test_reservation_references_are_unique_and_not_count_based(self):
        first = self._create(start=10, end=11)
        second = self._create(guest=self.other_guest, start=11, end=12)
        pattern = rf'^GDI-{self.today.year}-[A-F0-9]{{10}}$'
        self.assertRegex(first.reservation_number, pattern)
        self.assertRegex(second.reservation_number, pattern)
        self.assertNotEqual(first.reservation_number, second.reservation_number)

    def test_effective_daily_pricing_taxes_and_deposit_snapshot(self):
        DailyRate.objects.create(
            rate_plan=self.rate_plan, date=self.today + timedelta(days=2),
            price=Decimal('40000.00'),
        )
        TaxFee.objects.create(
            name='VAT', code='vat', calculation='percentage', amount=Decimal('7.50')
        )
        TaxFee.objects.create(
            name='Tourism Levy', code='tourism-levy', calculation='fixed', amount=Decimal('1000.00')
        )
        snapshot = calculate_quote(
            room=self.room, rate_plan=self.rate_plan,
            check_in_date=self.today + timedelta(days=2),
            check_out_date=self.today + timedelta(days=4),
        )
        self.assertEqual(snapshot['subtotal'], '70000.00')
        self.assertEqual(snapshot['tax_total'], '6250.00')
        self.assertEqual(snapshot['total'], '76250.00')
        self.assertEqual(snapshot['deposit_required'], '38125.00')

    def test_hold_blocks_other_sales_and_quote_converts_once(self):
        quote = create_quote(
            room=self.room, rate_plan=self.rate_plan,
            check_in_date=self.today + timedelta(days=5),
            check_out_date=self.today + timedelta(days=7),
            guest=self.guest, created_by=self.guest,
        )
        self.assertEqual(quote.hold.status, 'active')
        with self.assertRaises(ValidationError):
            create_quote(
                room=self.room, rate_plan=self.rate_plan,
                check_in_date=self.today + timedelta(days=6),
                check_out_date=self.today + timedelta(days=8),
                guest=self.other_guest,
            )
        with self.assertRaises(ReservationConflict):
            self._create(guest=self.other_guest, start=5, end=7)

        reservation = convert_quote(
            quote_id=quote.id, guest=self.guest, created_by=self.guest
        )
        quote.refresh_from_db()
        self.assertEqual(quote.status, 'converted')
        self.assertEqual(quote.converted_reservation, reservation)
        self.assertEqual(reservation.rate_plan, self.rate_plan)
        self.assertEqual(reservation.total_amount, quote.total)
        self.assertEqual(reservation.price_snapshot, quote.price_snapshot)
        with self.assertRaises(ValidationError):
            convert_quote(quote_id=quote.id, guest=self.guest)

    def test_expired_holds_are_released(self):
        quote = create_quote(
            room=self.room, rate_plan=self.rate_plan,
            check_in_date=self.today + timedelta(days=8),
            check_out_date=self.today + timedelta(days=9),
            guest=self.guest, ttl_minutes=-1,
        )
        self.assertEqual(expire_stale_holds(), 1)
        quote.refresh_from_db()
        quote.hold.refresh_from_db()
        self.assertEqual(quote.status, 'expired')
        self.assertEqual(quote.hold.status, 'expired')

    def test_stay_extension_posts_audited_folio_adjustment(self):
        reservation = self._create(start=2, end=4)
        transition_reservation(reservation_id=reservation.id, action='confirm', actor=self.staff)
        amended = amend_reservation_stay(
            reservation_id=reservation.id,
            check_in_date=self.today + timedelta(days=2),
            check_out_date=self.today + timedelta(days=5),
            num_adults=1, num_children=0, actor=self.staff,
            reason='Guest requested an extra night',
        )
        self.assertEqual(amended.check_out_date, self.today + timedelta(days=5))
        self.assertEqual(amended.total_amount, Decimal('90000.00'))
        self.assertEqual(amended.amendments.count(), 1)
        adjustment = amended.folio.entries.get(entry_type='adjustment')
        self.assertEqual(adjustment.amount, Decimal('30000.00'))

    def test_checked_in_room_move_releases_old_room_and_records_history(self):
        second_room = Room.objects.create(number='CMD-2', room_type=self.room_type)
        reservation = self._create(start=0, end=1)
        transition_reservation(reservation_id=reservation.id, action='confirm', actor=self.staff)
        transition_reservation(reservation_id=reservation.id, action='check_in', actor=self.staff)
        moved = move_reservation_room(
            reservation_id=reservation.id, new_room=second_room, actor=self.staff,
            reason='Air conditioner issue',
        )
        self.room.refresh_from_db()
        second_room.refresh_from_db()
        self.assertEqual(moved.room, second_room)
        self.assertEqual(self.room.status, 'housekeeping')
        self.assertEqual(second_room.status, 'occupied')
        self.assertEqual(moved.room_assignments.count(), 2)
        self.assertEqual(moved.amendments.get().action, 'room_move')
        self.assertTrue(HousekeepingTask.objects.filter(room=self.room, task_type='cleaning').exists())

    def test_waitlist_offer_converts_once_through_inventory_command(self):
        entry = WaitlistEntry.objects.create(
            guest=self.guest, room_type=self.room_type,
            check_in_date=self.today + timedelta(days=20),
            check_out_date=self.today + timedelta(days=22), created_by=self.staff,
        )
        entry = offer_waitlist_entry(entry_id=entry.id, actor=self.staff)
        self.assertEqual(entry.status, 'offered')
        reservation = convert_waitlist_entry(entry_id=entry.id, room=self.room, actor=self.staff)
        entry.refresh_from_db()
        self.assertEqual(entry.status, 'converted')
        self.assertEqual(entry.converted_reservation, reservation)
        with self.assertRaises(ValidationError):
            convert_waitlist_entry(entry_id=entry.id, room=self.room, actor=self.staff)
