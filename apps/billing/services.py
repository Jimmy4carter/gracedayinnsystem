from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Sum

from .models import FinancialCorrection, Folio, FolioEntry, Invoice, InvoiceItem


def _ensure_folio_entry(*, external_key, defaults, actor=None):
    entry, _created = FolioEntry.objects.get_or_create(
        external_key=external_key, defaults=defaults,
    )
    from .ledger import post_folio_journal
    post_folio_journal(entry=entry, actor=actor)
    return entry


@transaction.atomic
def ensure_invoice_for_reservation(reservation):
    """Create one invoice from the reservation's immutable commercial snapshot."""
    snapshot = reservation.price_snapshot or {}
    vat_rate = Decimal(str(snapshot.get('vat_rate', 0) or 0))
    vat_amount = Decimal(str(snapshot.get('vat_amount', 0) or 0))
    invoice, created = Invoice.objects.get_or_create(
        reservation=reservation,
        defaults={
            'guest': reservation.guest,
            'status': 'sent',
            'due_date': reservation.check_in_date,
            'notes': f'Generated for reservation {reservation.reservation_number}.',
            'tax_rate': vat_rate,
            'tax_amount': vat_amount,
            'vat_amount': vat_amount,
            'tax_amount_locked': True,
        },
    )
    if not created:
        return invoice

    InvoiceItem.objects.create(
        invoice=invoice,
        description=f'Accommodation charge ({reservation.reservation_number})',
        quantity=1,
        unit_price=Decimal(str(snapshot.get('subtotal', reservation.total_amount))),
    )
    for extra in snapshot.get('extras', []):
        amount = Decimal(str(extra.get('amount', 0)))
        if amount > 0:
            InvoiceItem.objects.create(
                invoice=invoice,
                description=extra.get('name', 'Booking extra'),
                quantity=1,
                unit_price=amount,
            )
    for tax in snapshot.get('taxes', []):
        if tax.get('source') == 'central_vat' or tax.get('code') == 'vat':
            continue
        amount = Decimal(str(tax.get('amount', 0)))
        if amount > 0:
            InvoiceItem.objects.create(
                invoice=invoice,
                description=tax.get('name', 'Tax/Fee'),
                quantity=1,
                unit_price=amount,
            )
    invoice.save()
    return invoice


@transaction.atomic
def ensure_folio_for_reservation(reservation, actor=None):
    folio, _ = Folio.objects.get_or_create(
        reservation=reservation,
        defaults={
            'guest': reservation.guest,
            'currency': reservation.price_snapshot.get('currency', settings.HOTEL_CURRENCY),
        },
    )
    snapshot = reservation.price_snapshot or {}
    accommodation = Decimal(str(snapshot.get('subtotal', reservation.total_amount)))
    if accommodation > 0:
        _ensure_folio_entry(
            external_key=f'reservation:{reservation.id}:accommodation',
            defaults={
                'folio': folio, 'direction': 'debit', 'entry_type': 'accommodation',
                'description': f'Accommodation {reservation.reservation_number}',
                'amount': accommodation, 'posted_by': actor,
            },
            actor=actor,
        )
    for index, tax in enumerate(snapshot.get('taxes', [])):
        amount = Decimal(str(tax['amount']))
        if amount > 0:
            _ensure_folio_entry(
                external_key=f'reservation:{reservation.id}:tax:{tax.get("code", index)}',
                defaults={
                    'folio': folio, 'direction': 'debit', 'entry_type': 'tax',
                    'description': tax.get('name', 'Tax/Fee'), 'amount': amount,
                    'metadata': tax, 'posted_by': actor,
                },
                actor=actor,
            )
    for index, extra in enumerate(snapshot.get('extras', [])):
        amount = Decimal(str(extra['amount']))
        if amount > 0:
            _ensure_folio_entry(
                external_key=f'reservation:{reservation.id}:extra:{extra.get("code", index)}',
                defaults={
                    'folio': folio, 'direction': 'debit', 'entry_type': 'service',
                    'description': extra.get('name', 'Booking extra'), 'amount': amount,
                    'metadata': extra, 'posted_by': actor,
                },
                actor=actor,
            )
    return folio


def post_folio_entry(*, folio, direction, entry_type, description, amount,
                     actor=None, external_key=None, metadata=None):
    entry = FolioEntry.objects.create(
        folio=folio, direction=direction, entry_type=entry_type,
        description=description, amount=amount, posted_by=actor,
        external_key=external_key, metadata=metadata or {},
    )
    from .ledger import post_folio_journal
    post_folio_journal(entry=entry, actor=actor)
    return entry


@transaction.atomic
def post_financial_correction(*, folio_id, kind, amount, reason, actor, requested_by=None):
    if not (actor.is_superuser or actor.role in {'admin', 'manager'}):
        raise ValidationError('Only managers or administrators can authorize financial corrections.')
    if kind not in {'adjustment', 'credit_note'}:
        raise ValidationError('Unknown financial correction type.')
    amount = Decimal(str(amount))
    if amount <= 0:
        raise ValidationError('Correction amount must be greater than zero.')
    if not reason.strip():
        raise ValidationError('A correction reason is required.')
    folio = Folio.objects.select_for_update().get(pk=folio_id)
    if folio.status != 'open':
        raise ValidationError('Financial corrections can only be posted to an open folio.')
    entry = post_folio_entry(
        folio=folio, direction='debit' if kind == 'adjustment' else 'credit',
        entry_type=kind, description=reason.strip(), amount=amount, actor=actor,
        metadata={'authorized_by': actor.id, 'requested_by': (requested_by or actor).id},
    )
    return FinancialCorrection.objects.create(
        folio=folio, entry=entry, kind=kind, reason=reason.strip(),
        requested_by=requested_by or actor, authorized_by=actor,
    )


def tax_summary(*, start_date=None, end_date=None):
    entries = FolioEntry.objects.filter(entry_type='tax', direction='debit')
    if start_date:
        entries = entries.filter(posted_at__date__gte=start_date)
    if end_date:
        entries = entries.filter(posted_at__date__lte=end_date)
    rows = entries.values('description').annotate(total=Sum('amount')).order_by('description')
    return {'rows': list(rows), 'total': entries.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')}
