from datetime import timedelta

from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase

from apps.accounts.models import UserProfile
from apps.frontend.models import AuditLog
from apps.payments.models import CashierTerminal
from apps.payments.services import record_payment, request_receipt_print
from apps.reservations.pricing import convert_quote, create_quote
from apps.reservations.services import transition_reservation
from apps.rooms.models import Room, RoomType


class ReceiptPrintingContractTests(APITestCase):
    def setUp(self):
        self.cashier = UserProfile.objects.create_user('print-cashier', role='receptionist', password='pass')
        self.guest = UserProfile.objects.create_user(
            'print-guest', first_name='A-Guest-With-An-Intentionally-Very-Long-First-Name',
            last_name='For-Thermal-Width-Verification', role='guest', password='pass',
        )
        self.other_guest = UserProfile.objects.create_user('print-other', role='guest', password='pass')
        room_type = RoomType.objects.create(name='Print Room', base_price='100.00', max_occupancy=2)
        room = Room.objects.create(number='PRINT-1', room_type=room_type)
        quote = create_quote(
            room=room, rate_plan=room_type.rate_plans.get(), check_in_date=timezone.localdate(),
            check_out_date=timezone.localdate() + timedelta(days=1), guest=self.guest,
        )
        reservation = convert_quote(quote_id=quote.id, guest=self.guest, created_by=self.cashier)
        reservation = transition_reservation(reservation_id=reservation.id, action='confirm', actor=self.cashier)
        _, self.receipt, _ = record_payment(
            invoice=reservation.invoice, amount=reservation.invoice.balance,
            method='bank_transfer', actor=self.cashier, idempotency_key='print-payment',
        )
        self.terminal = CashierTerminal.objects.create(
            code='print-pos', name='Print POS', receipt_width_mm=80
        )

    def test_thermal_html_contract_for_80_and_58_mm_and_reprint(self):
        job = request_receipt_print(receipt=self.receipt, terminal=self.terminal, actor=self.cashier)
        self.client.force_login(self.cashier)
        url = reverse('frontend:portal-payment-receipt', args=[self.receipt.id])
        response = self.client.get(url)
        self.assertContains(response, '@page { size: 80mm auto')
        self.assertContains(response, 'body { width: 72mm')
        self.assertContains(response, 'REPRINT COPY 2')
        self.assertContains(response, self.guest.first_name)

        self.terminal.receipt_width_mm = 58
        self.terminal.save(update_fields=['receipt_width_mm'])
        response = self.client.get(url)
        self.assertContains(response, '@page { size: 58mm auto')
        self.assertContains(response, 'body { width: 52mm')
        self.assertEqual(job.copy_number, 1)

    def test_guest_can_only_render_own_receipt(self):
        self.client.force_login(self.guest)
        url = reverse('frontend:portal-payment-receipt', args=[self.receipt.id])
        self.assertEqual(self.client.get(url).status_code, 200)
        self.client.force_login(self.other_guest)
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_a4_invoice_contract_displays_line_totals(self):
        self.client.force_login(self.guest)
        url = reverse('frontend:portal-invoice-print', args=[self.receipt.invoice_id])
        response = self.client.get(url)
        self.assertContains(response, '@page { size: A4')
        self.assertContains(response, 'Accommodation charge')
        self.assertContains(response, 'NGN 100.00')
        self.assertContains(response, self.guest.first_name)

    def test_print_failure_retry_and_success_are_api_audited(self):
        job = request_receipt_print(receipt=self.receipt, terminal=self.terminal, actor=self.cashier)
        self.client.force_authenticate(self.cashier)
        response = self.client.post(reverse('receipt-print-job-failed', args=[job.id]), {
            'error_message': 'Printer cover open',
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], 'failed')
        self.assertEqual(response.data['attempt_count'], 1)
        response = self.client.post(reverse('receipt-print-job-retry', args=[job.id]))
        self.assertEqual(response.data['status'], 'pending')
        response = self.client.post(reverse('receipt-print-job-printed', args=[job.id]))
        self.assertEqual(response.data['status'], 'printed')
        self.assertEqual(response.data['attempt_count'], 2)
        self.assertTrue(AuditLog.objects.filter(
            action='api_printed', target_model='ReceiptPrintJob', target_id=str(job.id),
        ).exists())
