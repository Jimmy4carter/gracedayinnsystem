from collections import Counter
from decimal import Decimal

from django.apps import apps
from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.db.models import F, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.billing.models import FolioEntry
from apps.housekeeping.models import StockBalance
from apps.payments.models import Payment
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
    refund_overages = []
    for payment in Payment.objects.annotate(
        refunded_total=Coalesce(Sum('refunds__amount'), Decimal('0.00'))
    ).filter(refunded_total__gt=F('amount')).values('id', 'amount', 'refunded_total'):
        refund_overages.append({
            'payment_id': payment['id'],
            'amount': str(payment['amount']),
            'refunded_total': str(payment['refunded_total']),
        })

    counts = Counter()
    for model in apps.get_models():
        counts[model._meta.label] = model._default_manager.count()

    issues = {
        'pending_migrations': _pending_migrations(),
        'reservation_conflicts': _reservation_conflicts(),
        'active_hold_conflicts': _active_hold_conflicts(now),
        'completed_payments_missing_folio': missing_folio,
        'completed_payments_missing_ledger_entry': missing_ledger,
        'refund_overages': refund_overages,
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
