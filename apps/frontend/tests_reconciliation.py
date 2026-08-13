from datetime import timedelta
from importlib import import_module
from io import StringIO

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.billing.models import FolioEntry, Invoice
from apps.payments.models import Payment
from apps.reservations.models import Reservation
from apps.rooms.models import Room, RoomType

from .reconciliation import reconcile_system


class SystemReconciliationTests(TestCase):
    def test_clean_database_produces_machine_readable_evidence(self):
        output = StringIO()
        call_command('reconcile_system', '--json', stdout=output)
        self.assertIn('"ok": true', output.getvalue())
        self.assertIn('System reconciliation passed.', output.getvalue())

    def test_overlapping_blocking_reservations_fail_reconciliation(self):
        guest = UserProfile.objects.create_user(
            username='reconcile-guest', role='guest', password='test-pass'
        )
        room_type = RoomType.objects.create(
            name='Reconciliation Room', base_price='100.00', max_occupancy=2
        )
        room = Room.objects.create(number='REC-1', room_type=room_type)
        arrival = timezone.localdate() + timedelta(days=10)
        for offset in (0, 1):
            Reservation.objects.create(
                guest=guest,
                room=room,
                check_in_date=arrival + timedelta(days=offset),
                check_out_date=arrival + timedelta(days=offset + 2),
                nightly_rate='100.00',
                status='confirmed',
            )

        result = reconcile_system()

        self.assertFalse(result['ok'])
        self.assertEqual(len(result['issues']['reservation_conflicts']), 1)
        with self.assertRaises(CommandError):
            call_command('reconcile_system', stdout=StringIO(), stderr=StringIO())

    def test_legacy_completed_payment_backfill_is_idempotent(self):
        guest = UserProfile.objects.create_user(
            username='legacy-payment-guest', role='guest', password='test-pass'
        )
        room_type = RoomType.objects.create(
            name='Legacy Payment Room', base_price='100.00', max_occupancy=2
        )
        room = Room.objects.create(number='LEG-1', room_type=room_type)
        arrival = timezone.localdate() + timedelta(days=10)
        reservation = Reservation.objects.create(
            guest=guest,
            room=room,
            check_in_date=arrival,
            check_out_date=arrival + timedelta(days=1),
            nightly_rate='100.00',
            status='confirmed',
        )
        invoice = Invoice.objects.create(reservation=reservation, guest=guest)
        payment = Payment.objects.create(
            invoice=invoice, amount='100.00', method='card', status='completed'
        )
        migration = import_module(
            'apps.payments.migrations.0004_backfill_completed_payment_ledgers'
        )

        migration.backfill_completed_payment_ledgers(apps, None)
        migration.backfill_completed_payment_ledgers(apps, None)

        payment.refresh_from_db()
        self.assertIsNotNone(payment.folio_id)
        self.assertEqual(
            FolioEntry.objects.filter(external_key=f'payment:{payment.id}').count(), 1
        )
        self.assertTrue(reconcile_system()['ok'])
