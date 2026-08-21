from datetime import timedelta
from decimal import Decimal
import tempfile

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.frontend.reporting import calculate_financial_report

from .expenditures import submit_expenditure, transition_expenditure
from .ledger import post_balanced_journal, reconcile_bank_account
from .models import BankAccount, Expenditure, ExpenseCategory, LedgerAccount


class ControlledExpenditureTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.manager = UserProfile.objects.create_user(
            username='expense-manager', password='test-pass', role='manager'
        )
        cls.accountant = UserProfile.objects.create_user(
            username='expense-accountant', password='test-pass', role='accountant'
        )
        cls.admin = UserProfile.objects.create_user(
            username='expense-admin', password='test-pass', role='admin'
        )
        cls.category = ExpenseCategory.objects.get(code='utilities')

    def submit(self, actor=None, amount='125000.00'):
        return submit_expenditure(
            actor=actor or self.manager, category=self.category,
            business_date=timezone.localdate(), vendor='Abuja Electricity Distribution',
            description='Monthly electricity supply', net_amount=amount,
            tax_amount='7500.00', payment_method='bank_transfer',
            external_reference='AEDC-2026-08',
        )

    def test_manager_submits_accountant_approves_and_payment_posts_balanced_journal(self):
        expenditure = self.submit()
        self.assertEqual(expenditure.status, 'submitted')
        self.assertEqual(expenditure.total_amount, Decimal('132500.00'))
        with self.assertRaises(ValidationError):
            transition_expenditure(
                expenditure_id=expenditure.id, action='approve', actor=self.manager
            )
        expenditure = transition_expenditure(
            expenditure_id=expenditure.id, action='approve', actor=self.accountant,
            note='Invoice and business purpose verified.',
        )
        self.assertEqual(expenditure.status, 'approved')
        expenditure = transition_expenditure(
            expenditure_id=expenditure.id, action='pay', actor=self.accountant,
            note='Bank transfer confirmed.',
        )
        self.assertEqual(expenditure.status, 'paid')
        self.assertIsNotNone(expenditure.journal_id)
        self.assertEqual(expenditure.journal.total_debits, Decimal('132500.00'))
        self.assertEqual(expenditure.journal.total_credits, Decimal('132500.00'))
        self.assertEqual(
            expenditure.journal.lines.get(account__code='1150').debit, Decimal('7500.00')
        )
        self.assertEqual(
            expenditure.journal.lines.get(account=self.category.ledger_account).debit,
            Decimal('125000.00'),
        )
        self.assertEqual(
            list(expenditure.status_events.values_list('to_status', flat=True)),
            ['submitted', 'approved', 'paid'],
        )

    def test_accountant_cannot_submit_and_rejection_requires_reason(self):
        with self.assertRaises(ValidationError):
            self.submit(actor=self.accountant)
        expenditure = self.submit()
        with self.assertRaises(ValidationError):
            transition_expenditure(
                expenditure_id=expenditure.id, action='reject', actor=self.accountant
            )
        with self.assertRaisesMessage(ValidationError, 'vendor reference is already recorded'):
            self.submit()

    def test_paid_expenses_feed_profit_and_category_reporting(self):
        expenditure = self.submit(amount='100000.00')
        transition_expenditure(
            expenditure_id=expenditure.id, action='approve', actor=self.accountant,
            note='Reviewed invoice.',
        )
        transition_expenditure(
            expenditure_id=expenditure.id, action='pay', actor=self.accountant,
            note='Payment confirmed.',
        )
        report = calculate_financial_report(days=7)
        self.assertEqual(report['operating_expenses'], Decimal('100000.00'))
        self.assertEqual(report['expense_cash_outflow'], Decimal('107500.00'))
        self.assertEqual(report['operating_profit'], Decimal('-100000.00'))
        self.assertEqual(report['input_tax_paid'], Decimal('7500.00'))
        self.assertEqual(report['net_tax_payable'], Decimal('-7500.00'))
        self.assertEqual(report['expense_by_category'][0]['category__name'], 'Utilities')

    def test_manager_portal_submits_and_accountant_exports_excel(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse('frontend:portal-expenditures'), {
            'action': 'submit', 'business_date': timezone.localdate().isoformat(),
            'category_id': self.category.id, 'vendor': 'Water Board',
            'description': 'Monthly water supply', 'net_amount': '50000.00',
            'tax_amount': '0', 'payment_method': 'bank_transfer',
            'external_reference': 'WB-52',
        })
        self.assertRedirects(response, reverse('frontend:portal-expenditures'))
        self.assertTrue(Expenditure.objects.filter(vendor='Water Board').exists())
        self.client.force_login(self.accountant)
        workbook = self.client.get(reverse('frontend:portal-reports-export-xlsx'))
        self.assertEqual(workbook.status_code, 200)
        self.assertEqual(
            workbook['Content-Type'],
            'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        self.assertGreater(len(workbook.content), 1000)

    def test_status_events_are_append_only(self):
        expenditure = self.submit()
        event = expenditure.status_events.get()
        event.note = 'tampered'
        with self.assertRaises(ValidationError):
            event.save()
        with self.assertRaises(ValidationError):
            event.delete()
        expenditure.net_amount = Decimal('1.00')
        with self.assertRaises(ValidationError):
            expenditure.save()
        with self.assertRaises(ValidationError):
            expenditure.delete()

    def test_accountant_portal_surfaces_are_connected_without_manager_only_links(self):
        self.client.force_login(self.accountant)
        dashboard = self.client.get(reverse('frontend:portal-dashboard'))
        self.assertEqual(dashboard.status_code, 200)
        self.assertContains(dashboard, 'Finance command strip')
        self.assertContains(dashboard, reverse('frontend:portal-expenditures'))
        self.assertContains(dashboard, reverse('frontend:portal-reports'))
        for route in (
            'portal-expenditures', 'portal-finance-controls', 'portal-reports',
            'portal-financial-audit',
        ):
            self.assertEqual(self.client.get(reverse(f'frontend:{route}')).status_code, 200)
        self.assertNotContains(dashboard, reverse('frontend:portal-management'))

    def test_bank_reconciliation_is_period_unique_and_accounting_controlled(self):
        bank_ledger = LedgerAccount.objects.create(
            code='1030', name='Operating bank', account_type='asset'
        )
        bank = BankAccount.objects.create(
            name='Operating account', bank_name='Test Bank', account_last_four='1234',
            ledger_account=bank_ledger,
        )
        post_balanced_journal(
            business_date=timezone.localdate(), source_type='TestDeposit', source_id='1',
            description='Opening deposit', external_key='test-bank-deposit', actor=self.accountant,
            lines=[{'account': '1030', 'debit': '1000'}, {'account': '4200', 'credit': '1000'}],
        )
        reconciliation = reconcile_bank_account(
            bank_account=bank, period_start=timezone.localdate(),
            period_end=timezone.localdate(), statement_balance='1000', actor=self.accountant,
        )
        self.assertEqual(reconciliation.status, 'balanced')
        self.assertEqual(reconciliation.difference, Decimal('0'))
        with self.assertRaises(ValidationError):
            reconcile_bank_account(
                bank_account=bank, period_start=timezone.localdate(),
                period_end=timezone.localdate(), statement_balance='1000', actor=self.accountant,
            )
        with self.assertRaises(ValidationError):
            reconcile_bank_account(
                bank_account=bank,
                period_start=timezone.localdate() - timedelta(days=1),
                period_end=timezone.localdate() - timedelta(days=1),
                statement_balance='0', actor=self.manager,
            )

    def test_evidence_is_downloaded_through_role_protected_view(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            expenditure = submit_expenditure(
                actor=self.manager, category=self.category, business_date=timezone.localdate(),
                vendor='Secure Vendor', description='Evidence test', net_amount='100',
                payment_method='cash',
                evidence=SimpleUploadedFile('receipt.pdf', b'%PDF-1.4 evidence', 'application/pdf'),
            )
            url = reverse('frontend:portal-expenditure-evidence', args=[expenditure.id])
            self.client.force_login(self.accountant)
            response = self.client.get(url)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response['Content-Disposition'], 'attachment; filename="receipt.pdf"')
            response.close()
            receptionist = UserProfile.objects.create_user(
                username='evidence-reception', password='test-pass', role='receptionist'
            )
            self.client.force_login(receptionist)
            self.assertEqual(self.client.get(url).status_code, 302)
