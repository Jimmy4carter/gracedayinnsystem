from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.rooms.models import BookableExtra, DailyRate, Promotion, RatePlan, Room, TaxFee

from .models import BookingQuote, BookingQuoteExtra, InventoryHold, Reservation
from .services import INVENTORY_BLOCKING_STATUSES, _validate_stay, create_reservation


MONEY_QUANTUM = Decimal('0.01')


def _money(value):
    return Decimal(value).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def expire_stale_holds(now=None):
    now = now or timezone.now()
    stale_quote_ids = list(InventoryHold.objects.filter(
        status='active', expires_at__lte=now
    ).values_list('quote_id', flat=True))
    InventoryHold.objects.filter(quote_id__in=stale_quote_ids).update(
        status='expired', released_at=now
    )
    BookingQuote.objects.filter(id__in=stale_quote_ids, status='active').update(status='expired')
    return len(stale_quote_ids)


@transaction.atomic
def release_quote(*, quote_id):
    quote = BookingQuote.objects.select_for_update().get(pk=quote_id)
    if quote.status != 'active':
        return quote
    now = timezone.now()
    quote.status = 'cancelled'
    quote.save(update_fields=['status'])
    InventoryHold.objects.filter(quote=quote, status='active').update(
        status='released', released_at=now
    )
    return quote


def _assert_inventory(room, check_in_date, check_out_date, exclude_quote_id=None):
    if Reservation.objects.filter(
        room=room,
        status__in=INVENTORY_BLOCKING_STATUSES,
        check_in_date__lt=check_out_date,
        check_out_date__gt=check_in_date,
    ).exists():
        raise ValidationError({'room': 'This room is unavailable for the selected dates.'})

    holds = InventoryHold.objects.filter(
        room=room,
        status='active',
        expires_at__gt=timezone.now(),
        quote__check_in_date__lt=check_out_date,
        quote__check_out_date__gt=check_in_date,
    )
    if exclude_quote_id:
        holds = holds.exclude(quote_id=exclude_quote_id)
    if holds.exists():
        raise ValidationError({'room': 'This room is temporarily held for another booking.'})
    from apps.rooms.inventory import overlapping_blocks
    if overlapping_blocks(room, check_in_date, check_out_date).exists():
        raise ValidationError({'room': 'This room is blocked from sale for the selected dates.'})


def _validate_promotion(promotion, *, room, nights, now=None):
    if not promotion:
        return
    now = now or timezone.now()
    if not promotion.is_active or not (promotion.valid_from <= now <= promotion.valid_to):
        raise ValidationError({'promotion_code': 'This promotion is not active.'})
    if promotion.minimum_nights > nights:
        raise ValidationError({'promotion_code': f'This promotion requires at least {promotion.minimum_nights} nights.'})
    if promotion.usage_limit is not None and promotion.times_used >= promotion.usage_limit:
        raise ValidationError({'promotion_code': 'This promotion has reached its usage limit.'})
    eligible_types = promotion.room_types.values_list('id', flat=True)
    if eligible_types.exists() and room.room_type_id not in eligible_types:
        raise ValidationError({'promotion_code': 'This promotion does not apply to this room type.'})


def calculate_quote(*, room, rate_plan, check_in_date, check_out_date, num_adults=1,
                    num_children=0, promotion=None, extras=()):
    if not rate_plan.is_active or rate_plan.room_type_id != room.room_type_id:
        raise ValidationError({'rate_plan': 'This rate plan is not available for the selected room.'})
    nights = (check_out_date - check_in_date).days
    if nights < rate_plan.min_stay or nights > rate_plan.max_stay:
        raise ValidationError({'check_out_date': f'Stay must be between {rate_plan.min_stay} and {rate_plan.max_stay} nights.'})
    if num_adults + num_children > room.room_type.max_occupancy:
        raise ValidationError({'num_adults': 'Guest count exceeds this room type’s maximum occupancy.'})

    dates = [check_in_date + timedelta(days=index) for index in range(nights)]
    overrides = {item.date: item for item in DailyRate.objects.filter(rate_plan=rate_plan, date__in=dates + [check_out_date])}
    arrival_rule = overrides.get(check_in_date)
    departure_rule = overrides.get(check_out_date)
    if arrival_rule and arrival_rule.closed_to_arrival:
        raise ValidationError({'check_in_date': 'This rate is closed to arrivals on the selected date.'})
    if departure_rule and departure_rule.closed_to_departure:
        raise ValidationError({'check_out_date': 'This rate is closed to departures on the selected date.'})

    nightly = []
    for night in dates:
        daily = overrides.get(night)
        if daily and daily.min_stay and nights < daily.min_stay:
            raise ValidationError({'check_out_date': f'A minimum {daily.min_stay}-night stay applies on {night}.'})
        price = daily.price if daily else room.room_type.base_price
        nightly.append({'date': night.isoformat(), 'amount': str(_money(price))})

    extra_adults = max(num_adults - rate_plan.included_adults, 0)
    occupant_lines = []
    occupant_total = Decimal('0.00')
    for code, name, quantity, unit_amount in [
        ('extra_adult', 'Additional adult supplement', extra_adults * nights, rate_plan.extra_adult_per_night),
        ('child', 'Child supplement', num_children * nights, rate_plan.child_per_night),
    ]:
        line_total = _money(Decimal(quantity) * unit_amount)
        if line_total:
            occupant_lines.append({
                'code': code, 'name': name, 'quantity': quantity,
                'unit_amount': str(_money(unit_amount)), 'amount': str(line_total),
            })
            occupant_total += line_total
    occupant_total = _money(occupant_total)
    room_total = sum((Decimal(item['amount']) for item in nightly), Decimal('0.00'))
    subtotal_before_discount = _money(room_total + occupant_total)
    _validate_promotion(promotion, room=room, nights=nights)
    discount = Decimal('0.00')
    if promotion:
        discount = _money(
            subtotal_before_discount * promotion.amount / Decimal('100')
            if promotion.discount_type == 'percentage' else promotion.amount
        )
        discount = min(discount, subtotal_before_discount)
    subtotal = _money(subtotal_before_discount - discount)
    extra_lines = []
    extra_total = Decimal('0.00')
    taxable_extra_total = Decimal('0.00')
    for extra in extras:
        if not extra.is_active:
            raise ValidationError({'extras': f'{extra.name} is not currently available.'})
        eligible_types = extra.room_types.values_list('id', flat=True)
        if eligible_types.exists() and room.room_type_id not in eligible_types:
            raise ValidationError({'extras': f'{extra.name} is not available for this room type.'})
        quantity = (
            1 if extra.pricing_model == 'per_stay'
            else nights if extra.pricing_model == 'per_night'
            else nights * (num_adults + num_children)
        )
        line_total = _money(extra.amount * quantity)
        extra_total += line_total
        if extra.taxable:
            taxable_extra_total += line_total
        extra_lines.append({
            'id': extra.id, 'code': extra.code, 'name': extra.name,
            'pricing_model': extra.pricing_model, 'quantity': quantity,
            'unit_amount': str(_money(extra.amount)), 'amount': str(line_total),
            'taxable': extra.taxable,
        })
    extra_total = _money(extra_total)
    taxable_base = subtotal + taxable_extra_total
    active_taxes = TaxFee.objects.filter(is_active=True).filter(
        Q(effective_from__isnull=True) | Q(effective_from__lte=check_in_date),
        Q(effective_to__isnull=True) | Q(effective_to__gte=check_in_date),
    )
    taxes = []
    tax_total = Decimal('0.00')
    for tax in active_taxes:
        calculated = _money(
            taxable_base * tax.amount / Decimal('100')
            if tax.calculation == 'percentage' else tax.amount
        )
        tax_total += calculated
        taxes.append({
            'code': tax.code, 'name': tax.name, 'calculation': tax.calculation,
            'rate_or_amount': str(tax.amount), 'amount': str(calculated),
        })
    tax_total = _money(tax_total)
    total = _money(subtotal + extra_total + tax_total)
    deposit = _money(total * rate_plan.deposit_percent / Decimal('100'))
    return {
        'currency': settings.HOTEL_CURRENCY,
        'nightly': nightly,
        'nights': nights,
        'subtotal_before_discount': str(subtotal_before_discount),
        'occupant_supplements': occupant_lines,
        'occupant_supplement_total': str(occupant_total),
        'promotion_code': promotion.code if promotion else '',
        'promotion_name': promotion.name if promotion else '',
        'discount_total': str(discount),
        'subtotal': str(subtotal),
        'extras': extra_lines,
        'extra_total': str(extra_total),
        'taxable_base': str(_money(taxable_base)),
        'taxes': taxes,
        'tax_total': str(tax_total),
        'total': str(total),
        'deposit_required': str(deposit),
        'room_type_id': room.room_type_id,
        'room_type_name': room.room_type.name,
        'rate_plan_id': rate_plan.id,
        'rate_plan_code': rate_plan.code,
    }


@transaction.atomic
def create_quote(*, room, rate_plan, check_in_date, check_out_date, num_adults=1,
                 num_children=0, guest=None, email='', created_by=None, ttl_minutes=15,
                 promotion_code='', extras=()):
    locked_room = Room.objects.select_for_update().select_related('room_type').get(pk=room.pk)
    locked_plan = RatePlan.objects.select_for_update().get(pk=rate_plan.pk)
    expire_stale_holds()
    _validate_stay(
        locked_room, check_in_date, check_out_date, num_adults, num_children
    )
    promotion = None
    if promotion_code:
        try:
            promotion = Promotion.objects.select_for_update().get(code__iexact=promotion_code.strip())
        except Promotion.DoesNotExist as exc:
            raise ValidationError({'promotion_code': 'Promotion code was not found.'}) from exc
    locked_extras = list(BookableExtra.objects.select_for_update().filter(
        pk__in=[item.pk for item in extras]
    ).prefetch_related('room_types'))
    snapshot = calculate_quote(
        room=locked_room, rate_plan=locked_plan,
        check_in_date=check_in_date, check_out_date=check_out_date,
        num_adults=num_adults, num_children=num_children, promotion=promotion,
        extras=locked_extras,
    )
    policy = {
        'rate_plan_code': locked_plan.code,
        'rate_plan_name': locked_plan.name,
        'cancellation_policy': locked_plan.cancellation_policy,
        'is_refundable': locked_plan.is_refundable,
        'deposit_percent': str(locked_plan.deposit_percent),
        'inclusions': locked_plan.inclusions,
        'free_cancellation_hours': locked_plan.free_cancellation_hours,
        'cancellation_fee_percent': str(locked_plan.cancellation_fee_percent),
        'included_adults': locked_plan.included_adults,
        'extra_adult_per_night': str(locked_plan.extra_adult_per_night),
        'child_per_night': str(locked_plan.child_per_night),
    }
    expires_at = timezone.now() + timedelta(minutes=ttl_minutes)
    quote = BookingQuote.objects.create(
        guest=guest, email=email or getattr(guest, 'email', ''), room=locked_room,
        rate_plan=locked_plan, check_in_date=check_in_date, check_out_date=check_out_date,
        num_adults=num_adults, num_children=num_children, currency=snapshot['currency'],
        subtotal=Decimal(snapshot['subtotal']), tax_total=Decimal(snapshot['tax_total']),
        total=Decimal(snapshot['total']), price_snapshot=snapshot, policy_snapshot=policy,
        promotion=promotion, discount_total=Decimal(snapshot['discount_total']),
        extra_total=Decimal(snapshot['extra_total']),
        expires_at=expires_at, created_by=created_by,
    )
    InventoryHold.objects.create(
        quote=quote, room=locked_room, expires_at=expires_at
    )
    BookingQuoteExtra.objects.bulk_create([
        BookingQuoteExtra(
            quote=quote, extra_id=line['id'], quantity=line['quantity'],
            unit_amount=Decimal(line['unit_amount']), total_amount=Decimal(line['amount']),
        ) for line in snapshot['extras']
    ])
    return quote


@transaction.atomic
def convert_quote(*, quote_id, guest, created_by=None, source='direct_website', notes=''):
    quote = BookingQuote.objects.select_for_update().select_related(
        'room', 'room__room_type', 'rate_plan', 'hold'
    ).get(pk=quote_id)
    if quote.status != 'active' or quote.expires_at <= timezone.now():
        if quote.status == 'active':
            quote.status = 'expired'
            quote.save(update_fields=['status'])
            InventoryHold.objects.filter(quote=quote).update(status='expired', released_at=timezone.now())
        raise ValidationError('This quote has expired or is no longer available.')

    locked_promotion = None
    if quote.promotion_id:
        locked_promotion = Promotion.objects.select_for_update().get(pk=quote.promotion_id)
        if locked_promotion.usage_limit is not None and locked_promotion.times_used >= locked_promotion.usage_limit:
            raise ValidationError('This promotion has reached its usage limit. Please request a new quote.')

    _assert_inventory(
        quote.room, quote.check_in_date, quote.check_out_date, exclude_quote_id=quote.id
    )
    average_rate = _money(quote.subtotal / max((quote.check_out_date - quote.check_in_date).days, 1))
    reservation = create_reservation(
        guest=guest, room=quote.room, rate_plan=quote.rate_plan,
        check_in_date=quote.check_in_date, check_out_date=quote.check_out_date,
        num_adults=quote.num_adults, num_children=quote.num_children,
        created_by=created_by, source=source, notes=notes,
        policy_snapshot=quote.policy_snapshot, price_snapshot=quote.price_snapshot,
        nightly_rate=average_rate, total_amount=quote.total,
        exclude_quote_id=quote.id,
    )
    quote.status = 'converted'
    quote.converted_reservation = reservation
    quote.save(update_fields=['status', 'converted_reservation'])
    quote.hold.status = 'converted'
    quote.hold.released_at = timezone.now()
    quote.hold.save(update_fields=['status', 'released_at'])
    if locked_promotion:
        locked_promotion.times_used += 1
        locked_promotion.save(update_fields=['times_used'])
    return reservation
