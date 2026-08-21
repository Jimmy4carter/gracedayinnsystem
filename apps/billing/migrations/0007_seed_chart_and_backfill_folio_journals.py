from django.db import migrations


DEFAULT_ACCOUNTS = {
    '1100': ('Guest receivables', 'asset'),
    '1010': ('Cash on hand', 'asset'),
    '1020': ('Bank / POS clearing', 'asset'),
    '2100': ('Tax payable', 'liability'),
    '4000': ('Room revenue', 'revenue'),
    '4100': ('Service revenue', 'revenue'),
    '4200': ('Other revenue', 'revenue'),
    '5100': ('Refunds and credits', 'expense'),
}


def seed_and_backfill(apps, schema_editor):
    LedgerAccount = apps.get_model('billing', 'LedgerAccount')
    JournalEntry = apps.get_model('billing', 'JournalEntry')
    JournalLine = apps.get_model('billing', 'JournalLine')
    FolioEntry = apps.get_model('billing', 'FolioEntry')
    Payment = apps.get_model('payments', 'Payment')
    PaymentRefund = apps.get_model('payments', 'PaymentRefund')

    accounts = {}
    for code, (name, account_type) in DEFAULT_ACCOUNTS.items():
        accounts[code], _created = LedgerAccount.objects.get_or_create(
            code=code, defaults={'name': name, 'account_type': account_type},
        )

    revenue_codes = {'accommodation': '4000', 'service': '4100', 'tax': '2100'}
    entries = FolioEntry.objects.exclude(entry_type__in=['payment', 'refund']).iterator()
    for entry in entries:
        external_key = f'folio-journal:{entry.external_key or entry.id}'
        if JournalEntry.objects.filter(external_key=external_key).exists():
            continue
        revenue_code = revenue_codes.get(entry.entry_type, '4200')
        journal = JournalEntry.objects.create(
            business_date=entry.posted_at.date(), source_type='FolioEntry',
            source_id=str(entry.id), description=entry.description[:255],
            external_key=external_key, posted_by_id=entry.posted_by_id,
        )
        if entry.direction == 'debit':
            lines = ((accounts['1100'], entry.amount, 0), (accounts[revenue_code], 0, entry.amount))
        else:
            lines = ((accounts[revenue_code], entry.amount, 0), (accounts['1100'], 0, entry.amount))
        JournalLine.objects.bulk_create([
            JournalLine(journal=journal, account=account, debit=debit, credit=credit)
            for account, debit, credit in lines
        ])

    for payment in Payment.objects.filter(status='completed').iterator():
        external_key = f'payment-journal:{payment.id}:receipt:{payment.amount}'
        if JournalEntry.objects.filter(external_key=external_key).exists():
            continue
        journal = JournalEntry.objects.create(
            business_date=payment.created_at.date(), source_type='Payment',
            source_id=str(payment.id), description=f'Payment {payment.reference}',
            external_key=external_key, posted_by_id=payment.processed_by_id,
        )
        debit_account = accounts['1010'] if payment.method == 'cash' else accounts['1020']
        JournalLine.objects.bulk_create([
            JournalLine(journal=journal, account=debit_account, debit=payment.amount),
            JournalLine(journal=journal, account=accounts['1100'], credit=payment.amount),
        ])

    for refund in PaymentRefund.objects.select_related('payment').order_by('id').iterator():
        payment = refund.payment
        external_key = f'payment-journal:{payment.id}:refund:{refund.id}'
        if JournalEntry.objects.filter(external_key=external_key).exists():
            continue
        legacy_key = f'payment-journal:{payment.id}:refund:{refund.amount}'
        legacy = JournalEntry.objects.filter(external_key=legacy_key).first()
        if legacy:
            legacy.external_key = external_key
            legacy.save(update_fields=['external_key'])
            continue
        journal = JournalEntry.objects.create(
            business_date=refund.created_at.date(), source_type='Payment',
            source_id=str(payment.id), description=f'Refund {payment.reference}',
            external_key=external_key, posted_by_id=refund.processed_by_id,
        )
        credit_account = accounts['1010'] if payment.method == 'cash' else accounts['1020']
        JournalLine.objects.bulk_create([
            JournalLine(journal=journal, account=accounts['1100'], debit=refund.amount),
            JournalLine(journal=journal, account=credit_account, credit=refund.amount),
        ])


class Migration(migrations.Migration):
    dependencies = [
        ('billing', '0006_invoice_tax_amount_locked_invoice_vat_amount_and_more'),
        ('payments', '0006_paymentstatusevent'),
    ]

    operations = [migrations.RunPython(seed_and_backfill, migrations.RunPython.noop)]
