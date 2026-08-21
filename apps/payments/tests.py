from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.billing.models import FolioEntry, Invoice, InvoiceItem, JournalEntry
from apps.reservations.models import Reservation
from apps.rooms.models import Room, RoomType

from .models import CashMovement, CashierTerminal, Payment, PaymentRefund, ReceiptPrintJob
from .services import (
    cashier_shift_summary, close_cashier_shift, open_cashier_shift,
    record_manual_cash_movement, record_payment, refund_payment, request_receipt_print,
)


class FinancialLedgerTests(TestCase):
    def setUp(self):
        self.cashier = UserProfile.objects.create_user(
            username='cashier', email='cashier@example.com', role='receptionist', password='test-pass'
        )
        self.manager = UserProfile.objects.create_user(
            username='manager-fin', email='manager-fin@example.com', role='manager', password='test-pass'
        )
        self.guest = UserProfile.objects.create_user(
            username='folio-guest', email='folio-guest@example.com', role='guest', password='test-pass'
        )
        room_type = RoomType.objects.create(name='Ledger Suite', base_price=Decimal('10000.00'))
        room = Room.objects.create(number='L-01', room_type=room_type)
        today = timezone.localdate()
        reservation = Reservation.objects.create(
            guest=self.guest, room=room, check_in_date=today + timedelta(days=1),
            check_out_date=today + timedelta(days=2), nightly_rate=Decimal('10000.00'),
            status='confirmed', created_by=self.cashier,
            price_snapshot={'subtotal': '10000.00', 'tax_total': '1000.00', 'total': '11000.00'},
        )
        self.invoice = Invoice.objects.create(
            reservation=reservation, guest=self.guest, status='sent', due_date=today
        )
        InvoiceItem.objects.create(
            invoice=self.invoice, description='Accommodation', quantity=1,
            unit_price=Decimal('10000.00')
        )
        self.invoice.save()
        self.terminal = CashierTerminal.objects.create(code='test-pos', name='Test POS')
        self.shift = open_cashier_shift(
            terminal=self.terminal, cashier=self.cashier, opening_float=Decimal('5000.00')
        )

    def test_cash_payment_is_idempotent_and_posts_every_ledger_once(self):
        payment, receipt, created = record_payment(
            invoice=self.invoice, amount=Decimal('5500.00'), method='cash',
            actor=self.cashier, idempotency_key='pay-once'
        )
        replay, replay_receipt, replay_created = record_payment(
            invoice=self.invoice, amount=Decimal('5500.00'), method='cash',
            actor=self.cashier, idempotency_key='pay-once'
        )
        self.assertTrue(created)
        self.assertFalse(replay_created)
        self.assertEqual(replay.pk, payment.pk)
        self.assertEqual(replay_receipt.pk, receipt.pk)
        self.assertEqual(Payment.objects.count(), 1)
        self.assertEqual(payment.folio.entries.filter(entry_type='payment').count(), 1)
        self.assertEqual(CashMovement.objects.filter(movement_type='sale').count(), 1)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, Decimal('5500.00'))

    def test_refund_is_idempotent_and_uses_compensating_entries(self):
        payment, _, _ = record_payment(
            invoice=self.invoice, amount=Decimal('5500.00'), method='cash',
            actor=self.cashier, idempotency_key='pay-refund'
        )
        refund, created = refund_payment(
            payment=payment, amount=Decimal('1000.00'), reason='Guest adjustment',
            actor=self.cashier, idempotency_key='refund-once'
        )
        replay, replay_created = refund_payment(
            payment=payment, amount=Decimal('1000.00'), reason='Guest adjustment',
            actor=self.cashier, idempotency_key='refund-once'
        )
        self.assertTrue(created)
        self.assertFalse(replay_created)
        self.assertEqual(replay.pk, refund.pk)
        self.assertEqual(PaymentRefund.objects.count(), 1)
        self.assertEqual(payment.folio.entries.filter(entry_type='refund').count(), 1)
        self.assertEqual(CashMovement.objects.filter(movement_type='refund').count(), 1)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.amount_paid, Decimal('4500.00'))

    def test_equal_partial_refunds_each_receive_a_distinct_balanced_journal(self):
        payment, _, _ = record_payment(
            invoice=self.invoice, amount=Decimal('2000.00'), method='cash',
            actor=self.cashier, idempotency_key='pay-equal-refunds'
        )
        first, _ = refund_payment(
            payment=payment, amount=Decimal('500.00'), reason='First adjustment',
            actor=self.cashier, idempotency_key='equal-refund-one'
        )
        second, _ = refund_payment(
            payment=payment, amount=Decimal('500.00'), reason='Second adjustment',
            actor=self.cashier, idempotency_key='equal-refund-two'
        )

        keys = {
            f'payment-journal:{payment.id}:refund:{first.id}',
            f'payment-journal:{payment.id}:refund:{second.id}',
        }
        journals = JournalEntry.objects.filter(external_key__in=keys)
        self.assertEqual(journals.count(), 2)
        for journal in journals:
            self.assertEqual(journal.total_debits, Decimal('500.00'))
            self.assertEqual(journal.total_credits, Decimal('500.00'))

    def test_financial_ledger_records_are_immutable(self):
        payment, _, _ = record_payment(
            invoice=self.invoice, amount=Decimal('1000.00'), method='cash',
            actor=self.cashier, idempotency_key='immutable-payment'
        )
        entry = payment.folio.entries.get(entry_type='payment')
        entry.description = 'Changed'
        with self.assertRaises(ValidationError):
            entry.save()
        with self.assertRaises(ValidationError):
            entry.delete()
        movement = CashMovement.objects.get(movement_type='sale')
        movement.notes = 'Changed'
        with self.assertRaises(ValidationError):
            movement.save()
        with self.assertRaises(ValidationError):
            movement.delete()

    @override_settings(CASH_VARIANCE_APPROVAL_THRESHOLD=Decimal('100.00'))
    def test_large_shift_variance_requires_authenticated_manager(self):
        with self.assertRaises(ValidationError):
            close_cashier_shift(
                shift=self.shift, counted_cash=Decimal('0.00'), actor=self.cashier
            )
        closed = close_cashier_shift(
            shift=self.shift, counted_cash=Decimal('0.00'), actor=self.manager,
            note='Manager verified shortage'
        )
        self.assertEqual(closed.status, 'approved')
        self.assertEqual(closed.approved_by, self.manager)
        self.assertEqual(closed.expected_cash, Decimal('5000.00'))
        self.assertEqual(closed.variance, Decimal('-5000.00'))

    def test_receipt_reprints_are_numbered(self):
        _, receipt, _ = record_payment(
            invoice=self.invoice, amount=Decimal('1000.00'), method='cash',
            actor=self.cashier, idempotency_key='print-payment'
        )
        first = request_receipt_print(receipt=receipt, terminal=self.terminal, actor=self.cashier)
        second = request_receipt_print(receipt=receipt, terminal=self.terminal, actor=self.cashier)
        self.assertEqual((first.copy_number, second.copy_number), (1, 2))
        self.assertEqual(ReceiptPrintJob.objects.filter(receipt=receipt).count(), 2)

    def test_manager_cash_movements_are_idempotent_and_in_x_z_reports(self):
        movement, created = record_manual_cash_movement(
            shift=self.shift, movement_type='paid_in', amount='250.00', actor=self.manager,
            notes='Extra float', idempotency_key='paid-in-once'
        )
        replay, replay_created = record_manual_cash_movement(
            shift=self.shift, movement_type='paid_in', amount='250.00', actor=self.manager,
            idempotency_key='paid-in-once'
        )
        self.assertTrue(created)
        self.assertFalse(replay_created)
        self.assertEqual(movement.pk, replay.pk)
        x_report = cashier_shift_summary(self.shift)
        self.assertEqual(x_report['report_type'], 'X')
        self.assertEqual(x_report['expected_cash'], Decimal('5250.00'))
        closed = close_cashier_shift(
            shift=self.shift, counted_cash='5250.00', actor=self.cashier
        )
        self.assertEqual(cashier_shift_summary(closed)['report_type'], 'Z')
