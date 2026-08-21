from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db.models import Sum
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.reservations.pricing import calculate_quote
from apps.reservations.services import create_reservation, transition_reservation
from apps.rooms.models import RatePlan, Room, RoomType

from .ledger import prepare_tax_liability
from .models import JournalLine, LedgerAccount, VATRateChange
from .vat import set_vat_rate


class VATControlTests(TestCase):
    def setUp(self):
        self.admin = UserProfile.objects.create_user(
            'vat-admin', email='vat-admin@example.com', role='admin', password='test-password-98X!'
        )
        self.admin.is_staff = True
        self.admin.save(update_fields=['is_staff'])
        self.guest = UserProfile.objects.create_user('vat-guest', role='guest')
        self.room_type = RoomType.objects.create(
            name='VAT Suite', base_price=Decimal('10000.00'), max_occupancy=2
        )
        self.room = Room.objects.create(number='VAT-1', room_type=self.room_type)
        self.plan = RatePlan.objects.create(
            room_type=self.room_type, name='VAT Flexible', code='vat-flex',
            min_stay=1, max_stay=10, deposit_percent=Decimal('50.00'),
        )
        self.arrival = timezone.localdate() + timedelta(days=3)

    def quote(self):
        return calculate_quote(
            room=self.room, rate_plan=self.plan,
            check_in_date=self.arrival, check_out_date=self.arrival + timedelta(days=1),
        )

    def test_positive_vat_is_snapshotted_and_printed(self):
        set_vat_rate(rate='7.50', reason='Current statutory rate', actor=self.admin)
        snapshot = self.quote()
        self.assertEqual(snapshot['vat_rate'], '7.50')
        self.assertEqual(snapshot['vat_amount'], '750.00')
        self.assertEqual(snapshot['total'], '10750.00')
        reservation = create_reservation(
            guest=self.guest, room=self.room, rate_plan=self.plan,
            check_in_date=self.arrival, check_out_date=self.arrival + timedelta(days=1),
            total_amount=Decimal(snapshot['total']), nightly_rate=Decimal('10000.00'),
            price_snapshot=snapshot, created_by=self.admin,
        )
        transition_reservation(reservation_id=reservation.id, action='confirm', actor=self.admin)
        invoice = reservation.invoice
        self.assertEqual(invoice.tax_rate, Decimal('7.50'))
        self.assertEqual(invoice.vat_amount, Decimal('750.00'))
        self.assertEqual(invoice.total, Decimal('10750.00'))
        self.client.force_login(self.admin)
        response = self.client.get(reverse('frontend:portal-invoice-print', args=[invoice.id]))
        self.assertContains(response, 'VAT (7.50%)')

    def test_front_desk_reservation_uses_current_vat_without_a_quote(self):
        set_vat_rate(rate='5.00', reason='Front desk VAT', actor=self.admin)
        reservation = create_reservation(
            guest=self.guest, room=self.room,
            check_in_date=self.arrival, check_out_date=self.arrival + timedelta(days=1),
            created_by=self.admin, source='front_desk',
        )
        self.assertEqual(reservation.price_snapshot['vat_rate'], '5.00')
        self.assertEqual(reservation.total_amount, Decimal('10500.00'))
        transition_reservation(reservation_id=reservation.id, action='confirm', actor=self.admin)
        self.assertEqual(reservation.invoice.vat_amount, Decimal('500.00'))
        self.assertEqual(reservation.invoice.total, Decimal('10500.00'))

    def test_zero_vat_is_absent_and_does_not_change_old_invoice(self):
        set_vat_rate(rate='7.50', reason='VAT on', actor=self.admin)
        old_snapshot = self.quote()
        set_vat_rate(rate='0', reason='VAT suspended', actor=self.admin)
        new_snapshot = self.quote()
        self.assertEqual(old_snapshot['vat_amount'], '750.00')
        self.assertEqual(new_snapshot['vat_amount'], '0.00')
        self.assertFalse(any(item.get('code') == 'vat' for item in new_snapshot['taxes']))

    def test_vat_history_is_append_only_and_admin_page_records_changes(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('frontend:portal-vat'), {
            'rate': '5.00', 'reason': 'Management-approved VAT rate',
        })
        self.assertRedirects(response, reverse('frontend:portal-vat'))
        change = VATRateChange.objects.get()
        self.assertEqual(change.rate, Decimal('5.00'))
        page = self.client.get(reverse('frontend:portal-vat'))
        self.assertContains(page, 'Management-approved VAT rate')
        change.rate = Decimal('6.00')
        with self.assertRaises(ValidationError):
            change.save()
        with self.assertRaises(ValidationError):
            change.delete()

    def test_tax_liability_snapshots_existing_payable_without_double_posting(self):
        set_vat_rate(rate='7.50', reason='Liability test', actor=self.admin)
        snapshot = self.quote()
        reservation = create_reservation(
            guest=self.guest, room=self.room, rate_plan=self.plan,
            check_in_date=self.arrival, check_out_date=self.arrival + timedelta(days=1),
            price_snapshot=snapshot, created_by=self.admin,
        )
        transition_reservation(reservation_id=reservation.id, action='confirm', actor=self.admin)
        payable = LedgerAccount.objects.get(code='2100')
        before = JournalLine.objects.filter(account=payable).aggregate(
            credits=Sum('credit'), debits=Sum('debit')
        )

        liability = prepare_tax_liability(
            tax_code='VAT', period_start=timezone.localdate(),
            period_end=timezone.localdate(), actor=self.admin,
        )
        after = JournalLine.objects.filter(account=payable).aggregate(
            credits=Sum('credit'), debits=Sum('debit')
        )

        self.assertEqual(liability.taxable_amount, Decimal('10000.00'))
        self.assertEqual(liability.tax_amount, Decimal('750.00'))
        self.assertIsNone(liability.journal)
        self.assertEqual(before, after)
