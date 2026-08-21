from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.billing.models import Invoice, Receipt
from apps.billing.services import ensure_folio_for_reservation, post_folio_entry
from apps.billing.ledger import post_payment_journal

from .models import (
    CashMovement, CashierShift, CashierTerminal, Payment, PaymentRefund, PaymentStatusEvent,
    ReceiptPrintJob,
)


def _money(value):
    return Decimal(str(value)).quantize(Decimal('0.01'))


@transaction.atomic
def open_cashier_shift(*, terminal, cashier, opening_float=0):
    locked_terminal = CashierTerminal.objects.select_for_update().get(pk=terminal.pk)
    if not locked_terminal.is_active:
        raise ValidationError('This cashier terminal is inactive.')
    if CashierShift.objects.filter(status='open').filter(
        terminal=locked_terminal
    ).exists() or CashierShift.objects.filter(status='open', cashier=cashier).exists():
        raise ValidationError('The terminal or cashier already has an open shift.')
    opening_float = _money(opening_float)
    if opening_float < 0:
        raise ValidationError('Opening float cannot be negative.')
    shift = CashierShift.objects.create(
        terminal=locked_terminal, cashier=cashier,
        opening_float=opening_float, expected_cash=opening_float,
    )
    if opening_float:
        CashMovement.objects.create(
            shift=shift, movement_type='opening_float', amount=opening_float,
            recorded_by=cashier, external_key=f'shift:{shift.id}:opening',
        )
    return shift


def get_open_shift(cashier):
    return CashierShift.objects.select_related('terminal').filter(
        cashier=cashier, status='open'
    ).first()


def cashier_shift_summary(shift):
    totals = {row['movement_type']: row['total'] for row in shift.cash_movements.values(
        'movement_type'
    ).annotate(total=Sum('amount'))}
    zero = Decimal('0.00')
    expected = (
        totals.get('opening_float', zero) + totals.get('sale', zero)
        + totals.get('paid_in', zero) - totals.get('refund', zero)
        - totals.get('paid_out', zero)
    )
    return {
        'shift_reference': str(shift.reference), 'status': shift.status,
        'terminal': shift.terminal.name, 'cashier': shift.cashier.username,
        'opened_at': shift.opened_at, 'closed_at': shift.closed_at,
        'opening_float': totals.get('opening_float', zero),
        'cash_sales': totals.get('sale', zero), 'cash_refunds': totals.get('refund', zero),
        'paid_in': totals.get('paid_in', zero), 'paid_out': totals.get('paid_out', zero),
        'expected_cash': expected, 'counted_cash': shift.counted_cash,
        'variance': shift.variance, 'report_type': 'X' if shift.status == 'open' else 'Z',
    }


@transaction.atomic
def record_manual_cash_movement(*, shift, movement_type, amount, actor, notes='', idempotency_key=None):
    if movement_type not in {'paid_in', 'paid_out'}:
        raise ValidationError('Only paid-in and paid-out manual movements are allowed.')
    if not actor.is_superuser and getattr(actor, 'role', None) not in {'admin', 'manager'}:
        raise ValidationError('A manager must authorize manual cash movements.')
    locked = CashierShift.objects.select_for_update().get(pk=shift.pk)
    if locked.status != 'open':
        raise ValidationError('Cash movements require an open shift.')
    if idempotency_key:
        existing = CashMovement.objects.filter(external_key=f'manual:{idempotency_key}').first()
        if existing:
            return existing, False
    movement = CashMovement.objects.create(
        shift=locked, movement_type=movement_type, amount=_money(amount), notes=notes,
        external_key=f'manual:{idempotency_key}' if idempotency_key else None,
        recorded_by=actor,
    )
    return movement, True


def _recalculate_invoice(invoice):
    payments_total = invoice.payments.filter(status__in=['completed', 'refunded']).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')
    refunds_total = PaymentRefund.objects.filter(payment__invoice=invoice).aggregate(
        total=Sum('amount')
    )['total'] or Decimal('0.00')
    amount_paid = _money(payments_total - refunds_total)
    balance = _money(invoice.total - amount_paid)
    status = 'paid' if balance <= 0 else ('partially_paid' if amount_paid > 0 else 'sent')
    Invoice.objects.filter(pk=invoice.pk).update(
        amount_paid=amount_paid, balance=balance, status=status
    )
    invoice.amount_paid, invoice.balance, invoice.status = amount_paid, balance, status


@transaction.atomic
def record_payment(*, invoice, amount, method, actor, idempotency_key,
                   transaction_id='', notes=''):
    if not idempotency_key:
        raise ValidationError('An idempotency key is required.')
    existing = Payment.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        return existing, existing.receipt, False
    locked_invoice = Invoice.objects.select_for_update().select_related('reservation').get(pk=invoice.pk)
    amount = _money(amount)
    if amount <= 0:
        raise ValidationError('Payment amount must be greater than zero.')
    if amount > locked_invoice.balance:
        raise ValidationError('Payment cannot exceed the outstanding balance.')
    shift = get_open_shift(actor) if method == 'cash' else None
    if method == 'cash' and not shift:
        raise ValidationError('Open a cashier shift before recording cash payments.')
    folio = ensure_folio_for_reservation(locked_invoice.reservation, actor=actor)
    payment = Payment.objects.create(
        invoice=locked_invoice, folio=folio, amount=amount, method=method,
        status='completed', transaction_id=transaction_id, notes=notes,
        processed_by=actor, cashier_shift=shift, idempotency_key=idempotency_key,
    )
    PaymentStatusEvent.objects.create(payment=payment, to_status='completed', actor=actor, metadata={'method': method})
    post_payment_journal(payment=payment, actor=actor)
    post_folio_entry(
        folio=folio, direction='credit', entry_type='payment',
        description=f'Payment {payment.reference}', amount=amount, actor=actor,
        external_key=f'payment:{payment.id}', metadata={'method': method},
    )
    receipt = Receipt.objects.create(
        invoice=locked_invoice, amount=amount,
        notes=f'Issued for payment {payment.reference}.',
    )
    Payment.objects.filter(pk=payment.pk).update(receipt=receipt)
    payment.receipt = receipt
    if shift:
        CashMovement.objects.create(
            shift=shift, movement_type='sale', amount=amount, recorded_by=actor,
            external_key=f'payment:{payment.id}', notes=payment.reference,
        )
    _recalculate_invoice(locked_invoice)
    return payment, receipt, True


@transaction.atomic
def refund_payment(*, payment, amount, reason, actor, idempotency_key):
    if not idempotency_key:
        raise ValidationError('An idempotency key is required.')
    existing = PaymentRefund.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        return existing, False
    locked_payment = Payment.objects.select_for_update().select_related(
        'invoice', 'folio'
    ).get(pk=payment.pk)
    if locked_payment.status not in {'completed', 'refunded'}:
        raise ValidationError('Only completed payments can be refunded.')
    amount = _money(amount)
    refunded = locked_payment.refunds.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
    if amount <= 0 or amount > locked_payment.amount - refunded:
        raise ValidationError('Refund exceeds the refundable payment balance.')
    shift = get_open_shift(actor) if locked_payment.method == 'cash' else None
    if locked_payment.method == 'cash' and not shift:
        raise ValidationError('Open a cashier shift before processing a cash refund.')
    refund = PaymentRefund.objects.create(
        payment=locked_payment, amount=amount, reason=reason,
        processed_by=actor, cashier_shift=shift, idempotency_key=idempotency_key,
    )
    PaymentStatusEvent.objects.create(
        payment=locked_payment, from_status=locked_payment.status,
        to_status='refunded' if refunded + amount == locked_payment.amount else locked_payment.status,
        actor=actor, reason=reason,
    )
    post_payment_journal(
        payment=locked_payment, actor=actor, refund=True, amount=amount,
        event_key=refund.id,
    )
    post_folio_entry(
        folio=locked_payment.folio, direction='debit', entry_type='refund',
        description=f'Refund {refund.reference}', amount=amount, actor=actor,
        external_key=f'refund:{refund.id}', metadata={'reason': reason},
    )
    if shift:
        CashMovement.objects.create(
            shift=shift, movement_type='refund', amount=amount, recorded_by=actor,
            external_key=f'refund:{refund.id}', notes=reason,
        )
    if refunded + amount == locked_payment.amount:
        Payment.objects.filter(pk=locked_payment.pk).update(status='refunded')
    _recalculate_invoice(locked_payment.invoice)
    return refund, True


@transaction.atomic
def close_cashier_shift(*, shift, counted_cash, actor, note='', approver=None):
    locked = CashierShift.objects.select_for_update().get(pk=shift.pk)
    is_manager = actor.is_superuser or getattr(actor, 'role', None) in {'admin', 'manager'}
    if locked.status != 'open' or (actor != locked.cashier and not is_manager):
        raise ValidationError('Only the assigned cashier or a manager can close an open shift.')
    expected = cashier_shift_summary(locked)['expected_cash']
    counted = _money(counted_cash)
    variance = _money(counted - expected)
    threshold = Decimal(str(getattr(settings, 'CASH_VARIANCE_APPROVAL_THRESHOLD', '1000.00')))
    if actor != locked.cashier and is_manager:
        approver = actor
    if abs(variance) > threshold:
        if not approver or approver == locked.cashier or (
            not approver.is_superuser and getattr(approver, 'role', None) not in {'admin', 'manager'}
        ):
            raise ValidationError('A manager must approve this cash variance.')
    locked.expected_cash = expected
    locked.counted_cash = counted
    locked.variance = variance
    locked.note = note
    locked.closed_at = timezone.now()
    locked.approved_by = approver
    locked.status = 'approved' if approver else 'closed'
    locked.save(update_fields=[
        'expected_cash', 'counted_cash', 'variance', 'note', 'closed_at',
        'approved_by', 'status',
    ])
    return locked


@transaction.atomic
def request_receipt_print(*, receipt, terminal, actor):
    copy_number = receipt.print_jobs.count() + 1
    return ReceiptPrintJob.objects.create(
        receipt=receipt, terminal=terminal, requested_by=actor, copy_number=copy_number
    )


@transaction.atomic
def record_print_result(*, job, success, actor, error_message=''):
    locked = ReceiptPrintJob.objects.select_for_update().get(pk=job.pk)
    if locked.status != 'pending':
        raise ValidationError('Only pending print jobs can record a result.')
    if not success and not error_message.strip():
        raise ValidationError('A print failure reason is required.')
    locked.attempt_count += 1
    locked.last_attempt_at = timezone.now()
    locked.status = 'printed' if success else 'failed'
    locked.error_message = '' if success else error_message.strip()[:255]
    locked.completed_at = timezone.now() if success else None
    locked.completed_by = actor
    locked.save(update_fields=[
        'attempt_count', 'last_attempt_at', 'status', 'error_message',
        'completed_at', 'completed_by',
    ])
    return locked


@transaction.atomic
def retry_print_job(*, job, actor):
    locked = ReceiptPrintJob.objects.select_for_update().get(pk=job.pk)
    if locked.status != 'failed':
        raise ValidationError('Only failed print jobs can be retried.')
    locked.status = 'pending'
    locked.error_message = ''
    locked.completed_by = None
    locked.save(update_fields=['status', 'error_message', 'completed_by'])
    return locked
