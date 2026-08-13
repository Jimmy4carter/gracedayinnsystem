from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.housekeeping.models import HousekeepingTask
from apps.payments.models import CashierTerminal
from apps.payments.services import (
    cashier_shift_summary, close_cashier_shift, open_cashier_shift,
    record_payment, request_receipt_print,
)
from apps.reservations.pricing import convert_quote, create_quote
from apps.reservations.services import transition_reservation
from apps.rooms.models import Room, RoomType


class HotelStayEndToEndTests(TestCase):
    def setUp(self):
        self.cashier = UserProfile.objects.create_user(
            'e2e-reception', role='receptionist', password='pass'
        )
        self.manager = UserProfile.objects.create_user(
            'e2e-manager', role='manager', password='pass'
        )
        self.guest = UserProfile.objects.create_user(
            'e2e-guest', email='guest@example.com', role='guest', password='pass'
        )
        room_type = RoomType.objects.create(name='E2E Standard', base_price='100.00', max_occupancy=2)
        self.room = Room.objects.create(number='E2E-1', room_type=room_type)
        self.rate_plan = room_type.rate_plans.get()
        self.terminal = CashierTerminal.objects.create(
            code='e2e-pos', name='E2E Front Desk', receipt_width_mm=80
        )

    def test_booking_to_checkout_receipt_and_balanced_shift(self):
        today = timezone.localdate()
        quote = create_quote(
            room=self.room, rate_plan=self.rate_plan, check_in_date=today,
            check_out_date=today + timedelta(days=1), guest=self.guest,
            created_by=self.cashier,
        )
        reservation = convert_quote(
            quote_id=quote.id, guest=self.guest, created_by=self.cashier,
            source='walk_in', notes='Counter booking end-to-end journey',
        )
        reservation = transition_reservation(
            reservation_id=reservation.id, action='confirm', actor=self.cashier
        )
        invoice = reservation.invoice
        self.assertEqual(invoice.total, Decimal('100.00'))

        shift = open_cashier_shift(
            terminal=self.terminal, cashier=self.cashier, opening_float='500.00'
        )
        payment, receipt, created = record_payment(
            invoice=invoice, amount=invoice.balance, method='cash', actor=self.cashier,
            idempotency_key='e2e-settlement', notes='Paid at front desk',
        )
        self.assertTrue(created)
        self.assertEqual(payment.folio.balance, Decimal('0.00'))
        print_job = request_receipt_print(
            receipt=receipt, terminal=self.terminal, actor=self.cashier
        )
        self.assertEqual(print_job.copy_number, 1)
        self.assertEqual(print_job.terminal.receipt_width_mm, 80)

        reservation = transition_reservation(
            reservation_id=reservation.id, action='check_in', actor=self.cashier
        )
        reservation.room.refresh_from_db()
        self.assertEqual(reservation.room.status, 'occupied')
        reservation = transition_reservation(
            reservation_id=reservation.id, action='check_out', actor=self.cashier
        )
        reservation.room.refresh_from_db()
        self.assertEqual(reservation.room.status, 'housekeeping')
        self.assertTrue(HousekeepingTask.objects.filter(
            room=self.room, task_type='cleaning', status='pending'
        ).exists())

        summary = cashier_shift_summary(shift)
        self.assertEqual(summary['expected_cash'], Decimal('600.00'))
        shift = close_cashier_shift(
            shift=shift, counted_cash='600.00', actor=self.cashier,
            note='End-to-end balanced close',
        )
        self.assertEqual(shift.status, 'closed')
        self.assertEqual(shift.variance, Decimal('0.00'))
        self.assertEqual(cashier_shift_summary(shift)['report_type'], 'Z')

    def test_cash_payment_requires_shift_and_is_idempotent(self):
        today = timezone.localdate()
        quote = create_quote(
            room=self.room, rate_plan=self.rate_plan, check_in_date=today,
            check_out_date=today + timedelta(days=1), guest=self.guest,
        )
        reservation = convert_quote(quote_id=quote.id, guest=self.guest, created_by=self.cashier)
        reservation = transition_reservation(
            reservation_id=reservation.id, action='confirm', actor=self.cashier
        )
        with self.assertRaises(ValidationError):
            record_payment(
                invoice=reservation.invoice, amount='100.00', method='cash',
                actor=self.cashier, idempotency_key='no-shift',
            )
        open_cashier_shift(terminal=self.terminal, cashier=self.cashier)
        first, receipt, created = record_payment(
            invoice=reservation.invoice, amount='100.00', method='cash',
            actor=self.cashier, idempotency_key='one-payment',
        )
        replay, replay_receipt, replay_created = record_payment(
            invoice=reservation.invoice, amount='100.00', method='cash',
            actor=self.cashier, idempotency_key='one-payment',
        )
        self.assertTrue(created)
        self.assertFalse(replay_created)
        self.assertEqual(replay, first)
        self.assertEqual(replay_receipt, receipt)
