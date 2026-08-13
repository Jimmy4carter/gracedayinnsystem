from django.db import migrations


def backfill_completed_payment_ledgers(apps, schema_editor):
    Payment = apps.get_model('payments', 'Payment')
    Folio = apps.get_model('billing', 'Folio')
    FolioEntry = apps.get_model('billing', 'FolioEntry')

    payments = Payment.objects.filter(status='completed').select_related(
        'invoice__reservation'
    ).order_by('id')
    for payment in payments.iterator():
        reservation = payment.invoice.reservation
        folio, _ = Folio.objects.get_or_create(
            reservation_id=reservation.id,
            defaults={
                'guest_id': reservation.guest_id,
                'currency': 'NGN',
                'status': 'open',
            },
        )
        if payment.folio_id != folio.id:
            Payment.objects.filter(pk=payment.pk).update(folio_id=folio.id)
        FolioEntry.objects.get_or_create(
            external_key=f'payment:{payment.id}',
            defaults={
                'folio_id': folio.id,
                'direction': 'credit',
                'entry_type': 'payment',
                'description': f'Legacy payment {payment.reference}',
                'amount': payment.amount,
                'posted_by_id': payment.processed_by_id,
                'metadata': {
                    'method': payment.method,
                    'migration': 'payments.0004_backfill_completed_payment_ledgers',
                },
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ('billing', '0003_financialcorrection'),
        ('payments', '0003_receiptprintjob_attempt_count_and_more'),
    ]

    operations = [
        migrations.RunPython(backfill_completed_payment_ledgers, migrations.RunPython.noop),
    ]
