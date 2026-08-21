from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import VATRateChange


ZERO_RATE = Decimal('0.00')


def current_vat_change(at=None):
    at = at or timezone.now()
    return VATRateChange.objects.filter(effective_at__lte=at).order_by(
        '-effective_at', '-id'
    ).first()


def current_vat_rate(at=None):
    change = current_vat_change(at=at)
    return change.rate if change else ZERO_RATE


@transaction.atomic
def set_vat_rate(*, rate, reason, actor):
    rate = Decimal(str(rate)).quantize(Decimal('0.01'))
    previous = current_vat_rate()
    return VATRateChange.objects.create(
        rate=rate,
        previous_rate=previous,
        reason=reason.strip(),
        changed_by=actor,
    )
