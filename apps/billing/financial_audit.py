import hashlib
import json
from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.payments.models import CashierShift, Payment, PaymentRefund

from .models import FinancialAuditRun, Folio, FolioEntry


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
    exceptions = []
    if open_shifts:
        exceptions.append({'code': 'open_shift', 'severity': 'high', 'count': open_shifts})
    if missing_receipts:
        exceptions.append({'code': 'missing_receipt', 'severity': 'high', 'count': missing_receipts})
    if missing_folio_links:
        exceptions.append({'code': 'missing_folio_link', 'severity': 'high', 'count': missing_folio_links})
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
