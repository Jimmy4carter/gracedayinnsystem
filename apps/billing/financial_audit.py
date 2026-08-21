import hashlib
import json
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.payments.models import CashierShift, Payment, PaymentRefund

from .models import Expenditure, FinancialAuditRun, Folio, FolioEntry, JournalEntry, JournalLine


def _money(value):
    return str(Decimal(str(value or 0)).quantize(Decimal('0.01')))


def collect_financial_controls(period_start: date, period_end: date):
    entries = FolioEntry.objects.filter(posted_at__date__range=(period_start, period_end))
    payments = Payment.objects.filter(created_at__date__range=(period_start, period_end))
    refunds = PaymentRefund.objects.filter(created_at__date__range=(period_start, period_end))
    shifts = CashierShift.objects.filter(opened_at__date__lte=period_end).filter(
        closed_at__date__gte=period_start) | CashierShift.objects.filter(
        opened_at__date__range=(period_start, period_end)
    )
    completed = payments.filter(status='completed')
    cash = completed.filter(method='cash').aggregate(total=Sum('amount'))['total'] or 0
    pos = completed.filter(method='pos').aggregate(total=Sum('amount'))['total'] or 0
    transfer = completed.filter(method='bank_transfer').aggregate(total=Sum('amount'))['total'] or 0
    online = completed.filter(method='online').aggregate(total=Sum('amount'))['total'] or 0
    debits = entries.filter(direction='debit').aggregate(total=Sum('amount'))['total'] or 0
    credits = entries.filter(direction='credit').aggregate(total=Sum('amount'))['total'] or 0
    refunds_total = refunds.aggregate(total=Sum('amount'))['total'] or 0
    variance = shifts.filter(status__in=['closed', 'approved']).aggregate(total=Sum('variance'))['total'] or 0
    open_shifts = shifts.filter(status='open').count()
    missing_receipts = completed.filter(receipt__isnull=True).count()
    missing_folio_links = completed.filter(folio__isnull=True).count()
    journals = list(
        JournalEntry.objects.filter(business_date__range=(period_start, period_end))
        .prefetch_related('lines')
    )
    journal_totals = [
        (
            sum((line.debit for line in journal.lines.all()), Decimal('0')),
            sum((line.credit for line in journal.lines.all()), Decimal('0')),
        )
        for journal in journals
    ]
    journal_debits = sum((debits for debits, _credits in journal_totals), Decimal('0'))
    journal_credits = sum((credits for _debits, credits in journal_totals), Decimal('0'))
    unbalanced_journals = sum(
        debits <= 0 or debits != credits for debits, credits in journal_totals
    )
    missing_payment_journals = sum(
        not JournalEntry.objects.filter(
            external_key=f'payment-journal:{payment.id}:receipt:{payment.amount}'
        ).exists()
        for payment in completed
    )
    charge_entries = entries.exclude(entry_type__in=['payment', 'refund'])
    missing_charge_journals = sum(
        not JournalEntry.objects.filter(
            external_key=f'folio-journal:{entry.external_key or entry.id}'
        ).exists()
        for entry in charge_entries
    )
    tax_lines = JournalLine.objects.filter(
        account__code='2100', journal__business_date__range=(period_start, period_end)
    ).aggregate(debits=Sum('debit'), credits=Sum('credit'))
    tax_payable = (tax_lines['credits'] or Decimal('0')) - (tax_lines['debits'] or Decimal('0'))
    input_tax_lines = JournalLine.objects.filter(
        account__code='1150', journal__business_date__range=(period_start, period_end),
    ).aggregate(debits=Sum('debit'), credits=Sum('credit'))
    input_tax_recoverable = (
        (input_tax_lines['debits'] or Decimal('0'))
        - (input_tax_lines['credits'] or Decimal('0'))
    )
    expenses = Expenditure.objects.filter(business_date__range=(period_start, period_end))
    paid_expenses = expenses.filter(status='paid')
    paid_expense_total = paid_expenses.aggregate(total=Sum('net_amount'))['total'] or 0
    expense_cash_outflow = paid_expenses.aggregate(total=Sum('total_amount'))['total'] or 0
    approved_expense_total = expenses.filter(status='approved').aggregate(total=Sum('total_amount'))['total'] or 0
    missing_expense_journals = paid_expenses.filter(journal__isnull=True).count()
    exceptions = []
    if open_shifts:
        exceptions.append({'code': 'open_shift', 'severity': 'high', 'count': open_shifts})
    if missing_receipts:
        exceptions.append({'code': 'missing_receipt', 'severity': 'high', 'count': missing_receipts})
    if missing_folio_links:
        exceptions.append({'code': 'missing_folio_link', 'severity': 'high', 'count': missing_folio_links})
    if missing_payment_journals:
        exceptions.append({'code': 'missing_payment_journal', 'severity': 'high', 'count': missing_payment_journals})
    if missing_charge_journals:
        exceptions.append({'code': 'missing_charge_journal', 'severity': 'high', 'count': missing_charge_journals})
    if unbalanced_journals:
        exceptions.append({'code': 'unbalanced_journal', 'severity': 'critical', 'count': unbalanced_journals})
    if missing_expense_journals:
        exceptions.append({'code': 'missing_expense_journal', 'severity': 'critical', 'count': missing_expense_journals})
    if expenses.filter(status='submitted').exists():
        exceptions.append({
            'code': 'expenses_awaiting_review', 'severity': 'medium',
            'count': expenses.filter(status='submitted').count(),
        })
    if variance:
        exceptions.append({'code': 'cash_variance', 'severity': 'medium', 'amount': _money(variance)})
    metrics = {
        'period_start': period_start.isoformat(), 'period_end': period_end.isoformat(),
        'folio_debits': _money(debits), 'folio_credits': _money(credits),
        'gross_collections': _money(cash + pos + transfer + online),
        'refunds': _money(refunds_total),
        'net_collections': _money(cash + pos + transfer + online - refunds_total),
        'tender': {'cash': _money(cash), 'pos': _money(pos), 'bank_transfer': _money(transfer), 'online': _money(online)},
        'payment_count': completed.count(), 'refund_count': refunds.count(),
        'open_receivables': _money(sum((max(f.balance, Decimal('0')) for f in Folio.objects.filter(status='open')), Decimal('0'))),
        'cash_variance': _money(variance), 'open_shift_count': open_shifts,
        'journal_debits': _money(journal_debits),
        'journal_credits': _money(journal_credits),
        'tax_payable': _money(tax_payable),
        'input_tax_recoverable': _money(input_tax_recoverable),
        'net_tax_payable': _money(tax_payable - input_tax_recoverable),
        'journal_count': len(journals),
        'paid_expenditure': _money(paid_expense_total),
        'expense_cash_outflow': _money(expense_cash_outflow),
        'approved_unpaid_expenditure': _money(approved_expense_total),
        'expenditure_count': paid_expenses.count(),
    }
    return metrics, exceptions


@transaction.atomic
def prepare_financial_audit(*, period_start, period_end, run_type='daily', actor):
    if period_end < period_start:
        raise ValidationError('Audit period end must be on or after the start date.')
    metrics, exceptions = collect_financial_controls(period_start, period_end)
    payload = json.dumps({'metrics': metrics, 'exceptions': exceptions}, sort_keys=True, separators=(',', ':'))
    return FinancialAuditRun.objects.create(
        period_start=period_start, period_end=period_end, run_type=run_type,
        metrics=metrics, exceptions=exceptions,
        source_hash=hashlib.sha256(payload.encode()).hexdigest(), prepared_by=actor,
    )


@transaction.atomic
def approve_financial_audit(*, audit_run, actor, note=''):
    if not (actor.is_superuser or actor.role in {'admin', 'manager'}):
        raise ValidationError('Only managers or administrators can approve a financial audit.')
    if audit_run.status != 'prepared':
        raise ValidationError('Only prepared audits can be approved.')
    if actor.pk == audit_run.prepared_by_id:
        raise ValidationError('A financial audit requires an independent reviewer.')
    FinancialAuditRun.objects.filter(pk=audit_run.pk).update(
        status='approved', approved_by=actor, approved_at=timezone.now(), reviewer_note=note.strip()
    )
    return FinancialAuditRun.objects.get(pk=audit_run.pk)
