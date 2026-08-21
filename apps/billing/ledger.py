from datetime import date
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from .models import BankReconciliation, JournalEntry, JournalLine, LedgerAccount, TaxLiability

DEFAULT_ACCOUNTS = {
    '1100': ('Guest receivables', 'asset'),
    '1150': ('Input VAT recoverable', 'asset'),
    '1010': ('Cash on hand', 'asset'),
    '1020': ('Bank / POS clearing', 'asset'),
    '2100': ('Tax payable', 'liability'),
    '4000': ('Room revenue', 'revenue'),
    '4100': ('Service revenue', 'revenue'),
    '4200': ('Other revenue', 'revenue'),
    '5100': ('Refunds and credits', 'expense'),
}


def account(code):
    existing = LedgerAccount.objects.filter(code=code, is_active=True).first()
    if existing:
        return existing
    if code not in DEFAULT_ACCOUNTS:
        raise ValidationError(f'Active ledger account {code} does not exist.')
    name, kind = DEFAULT_ACCOUNTS[code]
    return LedgerAccount.objects.get_or_create(
        code=code, defaults={'name': name, 'account_type': kind}
    )[0]


@transaction.atomic
def post_balanced_journal(*, business_date: date, source_type, source_id, description, external_key, lines, actor=None):
    existing = JournalEntry.objects.filter(external_key=external_key).first()
    if existing:
        return existing
    debit_total = sum((Decimal(str(item.get('debit', 0))) for item in lines), Decimal('0'))
    credit_total = sum((Decimal(str(item.get('credit', 0))) for item in lines), Decimal('0'))
    if debit_total <= 0 or debit_total != credit_total:
        raise ValidationError('Journal entry must balance with positive debit and credit totals.')
    journal = JournalEntry.objects.create(
        business_date=business_date, source_type=source_type, source_id=str(source_id),
        description=description[:255], external_key=external_key, posted_by=actor,
    )
    for item in lines:
        JournalLine.objects.create(
            journal=journal, account=account(item['account']),
            debit=Decimal(str(item.get('debit', 0))), credit=Decimal(str(item.get('credit', 0))),
            memo=item.get('memo', ''),
        )
    return journal


def post_folio_journal(*, entry, actor=None):
    if entry.entry_type in {'payment', 'refund'}:
        return None
    revenue_account = {'accommodation': '4000', 'service': '4100', 'tax': '2100'}.get(entry.entry_type, '4200')
    if entry.direction == 'debit':
        lines = [{'account': '1100', 'debit': entry.amount}, {'account': revenue_account, 'credit': entry.amount}]
    else:
        lines = [{'account': revenue_account, 'debit': entry.amount}, {'account': '1100', 'credit': entry.amount}]
    return post_balanced_journal(
        business_date=entry.posted_at.date(), source_type='FolioEntry', source_id=entry.id,
        description=entry.description, external_key=f'folio-journal:{entry.external_key or entry.id}', lines=lines, actor=actor,
    )


def post_payment_journal(*, payment, actor=None, refund=False, amount=None, event_key=None):
    amount = Decimal(str(amount if amount is not None else payment.amount))
    debit_account = '1010' if payment.method == 'cash' else '1020'
    if refund:
        lines = [{'account': '1100', 'debit': amount}, {'account': debit_account, 'credit': amount}]
    else:
        lines = [{'account': debit_account, 'debit': amount}, {'account': '1100', 'credit': amount}]
    return post_balanced_journal(
        business_date=payment.created_at.date(), source_type='Payment', source_id=payment.id,
        description=f'{"Refund" if refund else "Payment"} {payment.reference}',
        external_key=(
            f'payment-journal:{payment.id}:{"refund" if refund else "receipt"}:'
            f'{event_key if event_key is not None else amount}'
        ),
        lines=lines, actor=actor,
    )


@transaction.atomic
def prepare_tax_liability(*, tax_code, period_start, period_end, actor):
    from .models import FolioEntry, Invoice
    if not period_start or not period_end or period_end < period_start:
        raise ValidationError('A valid tax period is required.')
    if actor.role not in {'admin', 'accountant'}:
        raise ValidationError('Only accounting or an administrator can prepare tax liabilities.')
    existing = TaxLiability.objects.filter(
        tax_code__iexact=tax_code, period_start=period_start, period_end=period_end,
    ).first()
    if existing:
        return existing
    tax_entries = FolioEntry.objects.filter(
        entry_type='tax', direction='debit', posted_at__date__range=(period_start, period_end),
    )
    if tax_code:
        tax_entries = tax_entries.filter(description__icontains=tax_code)
    tax_amount = tax_entries.aggregate(total=Sum('amount'))['total'] or Decimal('0')
    if tax_amount <= 0:
        raise ValidationError('No tax entries exist in the selected period.')
    taxable_amount = Invoice.objects.filter(
        created_at__date__range=(period_start, period_end), tax_amount__gt=0,
    ).aggregate(total=Sum('subtotal'))['total'] or Decimal('0')
    return TaxLiability.objects.create(
        tax_code=tax_code, period_start=period_start, period_end=period_end,
        taxable_amount=taxable_amount, tax_amount=tax_amount, prepared_by=actor,
    )


def reconcile_bank_account(*, bank_account, period_start, period_end, statement_balance, actor, notes=''):
    if not period_start or not period_end or period_end < period_start:
        raise ValidationError('A valid bank reconciliation period is required.')
    if actor.role not in {'admin', 'accountant'}:
        raise ValidationError('Only accounting or an administrator can prepare bank reconciliations.')
    if BankReconciliation.objects.filter(
        bank_account=bank_account, period_start=period_start, period_end=period_end,
    ).exists():
        raise ValidationError('This bank account has already been reconciled for that period.')
    total = JournalLine.objects.filter(
        account=bank_account.ledger_account, journal__business_date__lte=period_end,
    ).aggregate(debit=Sum('debit'), credit=Sum('credit'))
    ledger_balance = (total['debit'] or Decimal('0')) - (total['credit'] or Decimal('0'))
    difference = Decimal(str(statement_balance)) - ledger_balance
    return BankReconciliation.objects.create(
        bank_account=bank_account, period_start=period_start, period_end=period_end,
        statement_balance=statement_balance, ledger_balance=ledger_balance, difference=difference,
        status='balanced' if difference == 0 else 'exception', prepared_by=actor, notes=notes,
    )
