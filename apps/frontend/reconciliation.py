from collections import Counter
from decimal import Decimal

from django.apps import apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.models import DecimalField, F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.billing.models import Expenditure, FolioEntry, JournalEntry
from apps.housekeeping.models import StockBalance
from apps.payments.models import Payment, PaymentRefund
from apps.reservations.models import InventoryHold, Reservation

from .audit import verify_audit_chain


BLOCKING_RESERVATION_STATUSES = ('pending', 'confirmed', 'checked_in')


def _pending_migrations():
    executor = MigrationExecutor(connection)
    targets = executor.loader.graph.leaf_nodes()
    return [f'{migration.app_label}.{migration.name}' for migration, _ in executor.migration_plan(targets)]


def _reservation_conflicts():
    conflicts = []
    rows = Reservation.objects.filter(
        room_id__isnull=False, status__in=BLOCKING_RESERVATION_STATUSES
    ).order_by('room_id', 'check_in_date', 'id').values(
        'id', 'room_id', 'check_in_date', 'check_out_date'
    )
    previous_by_room = {}
    for row in rows.iterator():
        previous = previous_by_room.get(row['room_id'])
        if previous and previous['check_out_date'] > row['check_in_date']:
            conflicts.append([previous['id'], row['id']])
            if row['check_out_date'] > previous['check_out_date']:
                previous_by_room[row['room_id']] = row
        else:
            previous_by_room[row['room_id']] = row
    return conflicts


def _active_hold_conflicts(now):
    holds = list(InventoryHold.objects.filter(
        status='active', expires_at__gt=now
    ).select_related('quote').order_by('room_id', 'quote__check_in_date', 'id'))
    conflicts = []
    previous_by_room = {}
    for hold in holds:
        previous = previous_by_room.get(hold.room_id)
        if previous and previous.quote.check_out_date > hold.quote.check_in_date:
            conflicts.append([previous.id, hold.id])
            if hold.quote.check_out_date > previous.quote.check_out_date:
                previous_by_room[hold.room_id] = hold
        else:
            previous_by_room[hold.room_id] = hold
    return conflicts


def reconcile_system():
    now = timezone.now()
    completed_payments = Payment.objects.filter(status='completed')
    missing_folio = list(completed_payments.filter(folio_id__isnull=True).values_list('id', flat=True))
    payment_ids = list(
        completed_payments.exclude(folio_id__isnull=True).values_list('id', flat=True)
    )
    existing_payment_entries = set(
        FolioEntry.objects.filter(
            external_key__in=[f'payment:{payment_id}' for payment_id in payment_ids]
        ).values_list('external_key', flat=True)
    )
    missing_ledger = [
        payment_id for payment_id in payment_ids
        if f'payment:{payment_id}' not in existing_payment_entries
    ]
    missing_payment_journals = [
        payment_id
        for payment_id, amount in completed_payments.values_list('id', 'amount')
        if not JournalEntry.objects.filter(
            external_key=f'payment-journal:{payment_id}:receipt:{amount}'
        ).exists()
    ]
    refunds = list(PaymentRefund.objects.values_list('id', 'payment_id'))
    existing_refund_journals = set(
        JournalEntry.objects.filter(
            external_key__in=[
                f'payment-journal:{payment_id}:refund:{refund_id}'
                for refund_id, payment_id in refunds
            ]
        ).values_list('external_key', flat=True)
    )
    missing_refund_journals = [
        refund_id for refund_id, payment_id in refunds
        if f'payment-journal:{payment_id}:refund:{refund_id}' not in existing_refund_journals
    ]
    charge_entries = list(
        FolioEntry.objects.exclude(entry_type__in=['payment', 'refund'])
        .values_list('id', 'external_key')
    )
    expected_charge_journals = {
        entry_id: f'folio-journal:{external_key or entry_id}'
        for entry_id, external_key in charge_entries
    }
    existing_charge_journals = set(
        JournalEntry.objects.filter(
            external_key__in=expected_charge_journals.values()
        ).values_list('external_key', flat=True)
    )
    missing_charge_journals = [
        entry_id for entry_id, external_key in expected_charge_journals.items()
        if external_key not in existing_charge_journals
    ]
    refund_overages = []
    for payment in Payment.objects.annotate(
        refunded_total=Coalesce(Sum('refunds__amount'), Decimal('0.00'))
    ).filter(refunded_total__gt=F('amount')).values('id', 'amount', 'refunded_total'):
        refund_overages.append({
            'payment_id': payment['id'],
            'amount': str(payment['amount']),
            'refunded_total': str(payment['refunded_total']),
        })

    journal_money = DecimalField(max_digits=14, decimal_places=2)
    journal_totals = JournalEntry.objects.annotate(
            reconciled_debits=Coalesce(
                Sum('lines__debit'), Decimal('0.00'), output_field=journal_money,
            ),
            reconciled_credits=Coalesce(
                Sum('lines__credit'), Decimal('0.00'), output_field=journal_money,
            ),
        ).values('id', 'reconciled_debits', 'reconciled_credits')
    unbalanced_journals = [
        row['id'] for row in journal_totals.iterator()
        if row['reconciled_debits'] <= 0
        or row['reconciled_debits'] != row['reconciled_credits']
    ]
    paid_expenses_missing_journal = list(
        Expenditure.objects.filter(status='paid', journal__isnull=True).values_list('id', flat=True)
    )
    expenses_missing_status_event = list(
        Expenditure.objects.filter(status_events__isnull=True).values_list('id', flat=True)
    )
    expenditure_total_mismatches = list(
        Expenditure.objects.exclude(
            total_amount=F('net_amount') + F('tax_amount')
        ).values_list('id', flat=True)
    )

    counts = Counter()
    for model in apps.get_models():
        counts[model._meta.label] = model._default_manager.count()

    issues = {
        'pending_migrations': _pending_migrations(),
        'reservation_conflicts': _reservation_conflicts(),
        'active_hold_conflicts': _active_hold_conflicts(now),
        'completed_payments_missing_folio': missing_folio,
        'completed_payments_missing_ledger_entry': missing_ledger,
        'completed_payments_missing_journal': missing_payment_journals,
        'refunds_missing_journal': missing_refund_journals,
        'folio_charges_missing_journal': missing_charge_journals,
        'refund_overages': refund_overages,
        'unbalanced_journals': unbalanced_journals,
        'paid_expenditures_missing_journal': paid_expenses_missing_journal,
        'expenditures_missing_status_event': expenses_missing_status_event,
        'expenditure_total_mismatches': expenditure_total_mismatches,
        'negative_stock_balances': list(
            StockBalance.objects.filter(quantity__lt=0).values_list('id', flat=True)
        ),
    }
    audit = verify_audit_chain()
    return {
        'database_vendor': connection.vendor,
        'checked_at': now.isoformat(),
        'ok': not any(issues.values()),
        'issues': issues,
        'counts': dict(sorted(counts.items())),
        'audit': audit,
    }
