from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from apps.accounts.models import UserProfile
from apps.frontend.models import AuditLog
from apps.reservations.models import Reservation
from apps.rooms.models import Room, RoomType

from .financial_audit import approve_financial_audit, prepare_financial_audit
from .models import FinancialAuditRun, FinancialCorrection, Folio, FolioEntry
from .services import post_financial_correction, tax_summary


class FinancialControlTests(APITestCase):
    def setUp(self):
        self.manager = UserProfile.objects.create_user('finance-manager', role='manager', password='pass')
        self.receptionist = UserProfile.objects.create_user('finance-frontdesk', role='receptionist', password='pass')
        self.guest = UserProfile.objects.create_user('finance-guest', role='guest', password='pass')
        room_type = RoomType.objects.create(name='Finance room', base_price='100.00', max_occupancy=2)
        room = Room.objects.create(number='FIN-1', room_type=room_type)
        today = timezone.localdate()
        reservation = Reservation.objects.create(
            guest=self.guest, room=room, check_in_date=today + timedelta(days=1),
            check_out_date=today + timedelta(days=2), nightly_rate='100.00', total_amount='100.00',
        )
        self.folio = Folio.objects.create(reservation=reservation, guest=self.guest)
        FolioEntry.objects.create(
            folio=self.folio, direction='debit', entry_type='tax',
            description='VAT', amount='7.50', posted_by=self.manager,
        )

    def test_compensating_entries_and_correction_records_are_immutable(self):
        debit = post_financial_correction(
            folio_id=self.folio.id, kind='adjustment', amount='25.00',
            reason='Correct omitted minibar charge', actor=self.manager,
        )
        credit = post_financial_correction(
            folio_id=self.folio.id, kind='credit_note', amount='10.00',
            reason='Correct duplicate service charge', actor=self.manager,
        )
        self.assertEqual(debit.entry.direction, 'debit')
        self.assertEqual(credit.entry.direction, 'credit')
        self.assertEqual(self.folio.balance, Decimal('22.50'))
        with self.assertRaises(ValidationError):
            credit.save()
        with self.assertRaises(ValidationError):
            credit.entry.delete()

    def test_receptionist_cannot_authorize_correction(self):
        with self.assertRaises(ValidationError):
            post_financial_correction(
                folio_id=self.folio.id, kind='credit_note', amount='5.00',
                reason='Attempt', actor=self.receptionist,
            )
        self.client.force_authenticate(self.receptionist)
        response = self.client.post(reverse('folio-credit-note', args=[self.folio.id]), {
            'amount': '5.00', 'reason': 'Attempt',
        })
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_manager_api_posts_and_reports_tax_from_ledger(self):
        self.client.force_authenticate(self.manager)
        response = self.client.post(reverse('folio-adjustment', args=[self.folio.id]), {
            'amount': '4.50', 'reason': 'Authorized correction',
        })
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(FinancialCorrection.objects.count(), 1)
        response = self.client.get(reverse('folio-tax-summary'))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total'], '7.50')
        self.assertTrue(AuditLog.objects.filter(action='api_adjustment').exists())

    def test_manager_portal_posts_audited_credit_note(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse('frontend:portal-billing'), {
            'folio_id': self.folio.id, 'kind': 'credit_note', 'amount': '3.00',
            'reason': 'Service recovery approved by duty manager',
        })
        self.assertRedirects(response, reverse('frontend:portal-billing'))
        correction = FinancialCorrection.objects.get()
        self.assertEqual(correction.authorized_by, self.manager)
        self.assertTrue(AuditLog.objects.filter(
            action='folio_credit_note', target_id=str(correction.id),
        ).exists())
        summary = tax_summary()
        self.assertEqual(summary['total'], Decimal('7.50'))

    def test_financial_audit_requires_independent_approval(self):
        run = prepare_financial_audit(
            period_start=timezone.localdate(), period_end=timezone.localdate(),
            actor=self.manager,
        )
        self.assertEqual(run.status, 'prepared')
        with self.assertRaises(ValidationError):
            approve_financial_audit(audit_run=run, actor=self.manager)
        with self.assertRaises(ValidationError):
            approve_financial_audit(audit_run=run, actor=self.receptionist)
        reviewer = UserProfile.objects.create_user('finance-reviewer', role='manager', password='pass')
        approved = approve_financial_audit(audit_run=run, actor=reviewer)
        self.assertEqual(approved.status, 'approved')
        self.assertEqual(FinancialAuditRun.objects.get(pk=run.pk).approved_by, reviewer)
