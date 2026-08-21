from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .ledger import post_balanced_journal
from .models import Expenditure, ExpenditureStatusEvent


TRANSITIONS = {
    'submitted': {'approve': 'approved', 'reject': 'rejected', 'void': 'void'},
    'approved': {'pay': 'paid', 'void': 'void'},
}


@transaction.atomic
def submit_expenditure(*, actor, category, business_date, vendor, description, net_amount,
                       tax_amount=0, payment_method, external_reference='', evidence=None):
    if actor.role not in {'admin', 'manager'}:
        raise ValidationError('Only an administrator or manager can submit expenditure.')
    vendor = vendor.strip()
    external_reference = external_reference.strip()
    if external_reference and Expenditure.objects.filter(
        vendor__iexact=vendor, external_reference__iexact=external_reference,
    ).exists():
        raise ValidationError('This vendor reference is already recorded.')
    expenditure = Expenditure(
        category=category, business_date=business_date, vendor=vendor,
        description=description.strip(), net_amount=Decimal(str(net_amount)),
        tax_amount=Decimal(str(tax_amount or 0)), payment_method=payment_method,
        external_reference=external_reference, submitted_by=actor,
    )
    if evidence:
        expenditure.evidence = evidence
    expenditure.save()
    ExpenditureStatusEvent.objects.create(
        expenditure=expenditure, from_status='', to_status='submitted', actor=actor,
        note='Expenditure submitted for independent accounting review.',
    )
    return expenditure


@transaction.atomic
def transition_expenditure(*, expenditure_id, action, actor, note=''):
    expenditure = Expenditure.objects.select_for_update().select_related(
        'category__ledger_account', 'submitted_by'
    ).get(pk=expenditure_id)
    target = TRANSITIONS.get(expenditure.status, {}).get(action)
    if not target:
        raise ValidationError(f'Cannot {action} an expenditure in {expenditure.status} status.')
    if action in {'approve', 'reject'}:
        if actor.role not in {'admin', 'accountant'}:
            raise ValidationError('Only accounting or an administrator can review expenditure.')
        if actor.pk == expenditure.submitted_by_id and not actor.is_superuser:
            raise ValidationError('The submitter cannot approve or reject their own expenditure.')
    elif action == 'pay':
        if actor.role not in {'admin', 'accountant'}:
            raise ValidationError('Only accounting or an administrator can record expenditure payment.')
    elif action == 'void' and actor.role != 'admin':
        raise ValidationError('Only an administrator can void expenditure.')
    if action in {'approve', 'reject', 'pay', 'void'} and not note.strip():
        raise ValidationError('A review or payment note is required for this action.')

    previous = expenditure.status
    expenditure.status = target
    update_fields = ['status', 'updated_at']
    if target == 'approved':
        expenditure.approved_by = actor
        expenditure.approved_at = timezone.now()
        update_fields += ['approved_by', 'approved_at']
    elif target == 'paid':
        debit_lines = [
            {'account': expenditure.category.ledger_account.code, 'debit': expenditure.net_amount}
        ]
        if expenditure.tax_amount:
            debit_lines.append({'account': '1150', 'debit': expenditure.tax_amount})
        journal = post_balanced_journal(
            business_date=expenditure.business_date,
            source_type='Expenditure', source_id=expenditure.id,
            description=f'Expenditure {str(expenditure.reference)[:8]} — {expenditure.vendor}',
            external_key=f'expenditure-journal:{expenditure.id}', actor=actor,
            lines=debit_lines + [
                {
                    'account': '1010' if expenditure.payment_method == 'cash' else '1020',
                    'credit': expenditure.total_amount,
                },
            ],
        )
        expenditure.paid_by = actor
        expenditure.paid_at = timezone.now()
        expenditure.journal = journal
        update_fields += ['paid_by', 'paid_at', 'journal']
    expenditure.save(update_fields=update_fields)
    ExpenditureStatusEvent.objects.create(
        expenditure=expenditure, from_status=previous, to_status=target,
        actor=actor, note=note.strip(),
    )
    return expenditure
