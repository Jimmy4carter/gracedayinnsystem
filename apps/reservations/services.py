from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from datetime import datetime, time, timedelta

from apps.billing.models import Invoice, InvoiceItem
from apps.housekeeping.models import HousekeepingTask
from apps.notifications.models import Notification
from apps.rooms.models import Room

from .models import Reservation, ReservationRoomAssignment, ReservationStatusHistory


INVENTORY_BLOCKING_STATUSES = {'pending', 'confirmed', 'checked_in'}


class ReservationConflict(ValidationError):
    pass


class InvalidReservationTransition(ValidationError):
    pass


def _validate_stay(room, check_in_date, check_out_date, num_adults, num_children,
                   exclude_id=None, exclude_quote_id=None, allow_past_arrival=False):
    if check_in_date < timezone.localdate() and not allow_past_arrival:
        raise ValidationError({'check_in_date': 'Check-in date cannot be in the past.'})
    if check_out_date <= check_in_date:
        raise ValidationError({'check_out_date': 'Check-out must be after check-in.'})
    if not room.is_active or not room.is_sellable:
        raise ValidationError({'room': 'This room is not available for sale.'})
    if num_adults + num_children > room.room_type.max_occupancy:
        raise ValidationError({'num_adults': 'Guest count exceeds this room type’s maximum occupancy.'})

    conflicts = Reservation.objects.filter(
        room=room,
        status__in=INVENTORY_BLOCKING_STATUSES,
        check_in_date__lt=check_out_date,
        check_out_date__gt=check_in_date,
    )
    if exclude_id:
        conflicts = conflicts.exclude(pk=exclude_id)
    if conflicts.exists():
        raise ReservationConflict({'room': 'This room is unavailable for the selected dates.'})
    from .models import InventoryHold
    holds = InventoryHold.objects.filter(
        room=room, status='active', expires_at__gt=timezone.now(),
        quote__check_in_date__lt=check_out_date, quote__check_out_date__gt=check_in_date,
    )
    if exclude_quote_id:
        holds = holds.exclude(quote_id=exclude_quote_id)
    if holds.exists():
        raise ReservationConflict({'room': 'This room is temporarily held for another booking.'})
    from apps.rooms.inventory import overlapping_blocks
    if overlapping_blocks(room, check_in_date, check_out_date).exists():
        raise ReservationConflict({'room': 'This room is blocked from sale for the selected dates.'})


@transaction.atomic
def create_reservation(*, guest, room, check_in_date, check_out_date, created_by=None,
                       num_adults=1, num_children=0, special_requests='', notes='',
                       source='admin', channel_reference='', policy_snapshot=None,
                       price_snapshot=None, rate_plan=None, nightly_rate=None,
                       total_amount=None, exclude_quote_id=None, corporate_account=None,
                       group_booking=None):
    locked_room = Room.objects.select_for_update().select_related('room_type').get(pk=room.pk)
    _validate_stay(
        locked_room, check_in_date, check_out_date, num_adults, num_children,
        exclude_quote_id=exclude_quote_id,
    )
    nights = (check_out_date - check_in_date).days
    reservation = Reservation.objects.create(
        guest=guest,
        room=locked_room,
        check_in_date=check_in_date,
        check_out_date=check_out_date,
        num_adults=num_adults,
        num_children=num_children,
        special_requests=special_requests,
        notes=notes,
        nightly_rate=nightly_rate or locked_room.current_price,
        total_amount=total_amount or 0,
        rate_plan=rate_plan,
        status='pending',
        created_by=created_by,
        source=source,
        channel_reference=channel_reference,
        corporate_account=corporate_account,
        group_booking=group_booking,
        price_snapshot=price_snapshot or {
            'currency': settings.HOTEL_CURRENCY,
            'nightly_rate': str(locked_room.current_price),
            'nights': nights,
            'subtotal': str(locked_room.current_price * nights),
            'room_type_id': locked_room.room_type_id,
            'room_type_name': locked_room.room_type.name,
            'total': str(locked_room.current_price * nights),
        },
        policy_snapshot=policy_snapshot or {},
    )
    ReservationStatusHistory.objects.create(
        reservation=reservation,
        from_status='',
        to_status='pending',
        action='create',
        actor=created_by,
        metadata={'source': source},
    )
    ReservationRoomAssignment.objects.create(
        reservation=reservation,
        room=locked_room,
        assigned_by=created_by,
        reason='initial_assignment',
    )
    return reservation


def _ensure_invoice(reservation):
    from apps.billing.services import ensure_folio_for_reservation
    invoice, created = Invoice.objects.get_or_create(
        reservation=reservation,
        defaults={
            'guest': reservation.guest,
            'status': 'sent',
            'due_date': reservation.check_in_date,
            'notes': f'Generated for reservation {reservation.reservation_number}.',
            'tax_rate': 0,
        },
    )
    if created:
        snapshot = reservation.price_snapshot or {}
        InvoiceItem.objects.create(
            invoice=invoice,
            description=f'Accommodation charge ({reservation.reservation_number})',
            quantity=1,
            unit_price=snapshot.get('subtotal', reservation.total_amount),
        )
        for tax in snapshot.get('taxes', []):
            InvoiceItem.objects.create(
                invoice=invoice, description=tax['name'], quantity=1, unit_price=tax['amount']
            )
        invoice.save()
    ensure_folio_for_reservation(reservation, actor=reservation.created_by)
    return invoice


@transaction.atomic
def transition_reservation(*, reservation_id, action, actor=None):
    reservation = Reservation.objects.select_for_update().select_related(
        'guest', 'room', 'room__room_type'
    ).get(pk=reservation_id)
    room = Room.objects.select_for_update().get(pk=reservation.room_id)

    allowed = {
        'confirm': ({'pending'}, 'confirmed'),
        'check_in': ({'confirmed'}, 'checked_in'),
        'check_out': ({'checked_in'}, 'checked_out'),
        'cancel': ({'pending', 'confirmed'}, 'cancelled'),
        'no_show': ({'confirmed'}, 'no_show'),
    }
    if action not in allowed:
        raise InvalidReservationTransition('Unknown reservation action.')
    allowed_from, next_status = allowed[action]
    if reservation.status not in allowed_from:
        raise InvalidReservationTransition(
            f'Reservation cannot move from {reservation.status} to {next_status}.'
        )

    if action in {'confirm', 'check_in'}:
        _validate_stay(
            room,
            reservation.check_in_date,
            reservation.check_out_date,
            reservation.num_adults,
            reservation.num_children,
            exclude_id=reservation.pk,
        )

    previous_status = reservation.status

    if action == 'confirm':
        invoice = _ensure_invoice(reservation)
        Notification.objects.create(
            recipient=reservation.guest,
            title='Reservation confirmed',
            message=(f'Your reservation {reservation.reservation_number} is confirmed. '
                     f'Invoice {invoice.invoice_number} has been generated.'),
            notification_type='reservation',
            link='/portal/billing/',
        )
    elif action == 'check_in':
        reservation.actual_check_in = timezone.now()
        room.status = 'occupied'
        room.save(update_fields=['status'])
    elif action == 'check_out':
        reservation.actual_check_out = timezone.now()
        room.status = 'housekeeping'
        room.save(update_fields=['status'])
        if not HousekeepingTask.objects.filter(room=room, status__in=['pending', 'in_progress'], task_type='cleaning').exists():
            from apps.housekeeping.services import create_housekeeping_task
            create_housekeeping_task(
                room=room, task_type='cleaning', priority='high', actor=actor,
                notes=f'Auto-created at checkout for reservation {reservation.reservation_number}.',
            )
        reservation.room_assignments.filter(released_at__isnull=True).update(
            released_at=timezone.now()
        )

    cancellation_metadata = {}
    if action == 'cancel':
        policy = reservation.policy_snapshot or {}
        fee_percent = Decimal(str(policy.get('cancellation_fee_percent', '0')))
        free_hours = int(policy.get('free_cancellation_hours', 0) or 0)
        is_refundable = bool(policy.get('is_refundable', True))
        cutoff = timezone.make_aware(datetime.combine(reservation.check_in_date, time.min)) - timedelta(hours=free_hours)
        if not is_refundable:
            fee_percent = Decimal('100')
        elif timezone.now() < cutoff:
            fee_percent = Decimal('0')
        fee = (reservation.total_amount * fee_percent / Decimal('100')).quantize(Decimal('0.01'))
        reservation.cancellation_fee = fee
        cancellation_metadata = {
            'fee_percent': str(fee_percent), 'fee_amount': str(fee),
            'free_cancellation_hours': free_hours, 'cutoff': cutoff.isoformat(),
        }
        if reservation.total_amount > 0:
            from apps.billing.services import ensure_folio_for_reservation, post_folio_entry
            folio = ensure_folio_for_reservation(reservation, actor=actor)
            post_folio_entry(
                folio=folio, direction='credit', entry_type='credit_note',
                description=f'Cancellation reversal {reservation.reservation_number}',
                amount=reservation.total_amount, actor=actor,
                external_key=f'reservation:{reservation.id}:cancellation-reversal',
                metadata=cancellation_metadata,
            )
            if fee > 0:
                post_folio_entry(
                    folio=folio, direction='debit', entry_type='adjustment',
                    description=f'Cancellation fee {reservation.reservation_number}',
                    amount=fee, actor=actor,
                    external_key=f'reservation:{reservation.id}:cancellation-fee',
                    metadata=cancellation_metadata,
                )

    if action != 'confirm':
        titles = {
            'check_in': 'Checked in', 'check_out': 'Checked out',
            'cancel': 'Reservation cancelled', 'no_show': 'Reservation marked no-show',
        }
        Notification.objects.create(
            recipient=reservation.guest,
            title=titles[action],
            message=f'Reservation {reservation.reservation_number} is now {next_status.replace("_", " ")}.',
            notification_type='reservation',
            link='/portal/reservations/',
        )

    reservation.status = next_status
    reservation.save()
    ReservationStatusHistory.objects.create(
        reservation=reservation,
        from_status=previous_status,
        to_status=next_status,
        action=action,
        actor=actor, metadata=cancellation_metadata,
    )
    return reservation


@transaction.atomic
def move_reservation_room(*, reservation_id, new_room, actor, reason):
    reservation = Reservation.objects.select_for_update().select_related('room', 'guest').get(pk=reservation_id)
    if reservation.status not in {'confirmed', 'checked_in'}:
        raise ValidationError('Only confirmed or checked-in reservations can move rooms.')
    old_room = Room.objects.select_for_update().get(pk=reservation.room_id)
    target = Room.objects.select_for_update().select_related('room_type').get(pk=new_room.pk)
    if target.pk == old_room.pk:
        raise ValidationError('Select a different room.')
    _validate_stay(
        target, reservation.check_in_date, reservation.check_out_date,
        reservation.num_adults, reservation.num_children,
    )
    before = {'room_id': old_room.id, 'room_number': old_room.number}
    reservation.room_assignments.filter(released_at__isnull=True).update(released_at=timezone.now())
    reservation.room = target
    reservation.save(update_fields=['room', 'updated_at'])
    ReservationRoomAssignment.objects.create(
        reservation=reservation, room=target, assigned_by=actor, reason=reason or 'room_move'
    )
    from .models import ReservationAmendmentHistory
    ReservationAmendmentHistory.objects.create(
        reservation=reservation, action='room_move', before=before,
        after={'room_id': target.id, 'room_number': target.number},
        reason=reason or 'Room move', actor=actor,
    )
    if reservation.status == 'checked_in':
        old_room.status, target.status = 'housekeeping', 'occupied'
        old_room.save(update_fields=['status'])
        target.save(update_fields=['status'])
        from apps.housekeeping.services import create_housekeeping_task
        create_housekeeping_task(
            room=old_room, task_type='cleaning', priority='high', actor=actor,
            notes=f'Room move cleanup for {reservation.reservation_number}.',
        )
    return reservation


@transaction.atomic
def amend_reservation_stay(*, reservation_id, check_in_date, check_out_date,
                           num_adults, num_children, actor, reason):
    reservation = Reservation.objects.select_for_update().select_related('room', 'rate_plan').get(pk=reservation_id)
    if reservation.status not in {'pending', 'confirmed', 'checked_in'}:
        raise ValidationError('This reservation can no longer be amended.')
    room = Room.objects.select_for_update().select_related('room_type').get(pk=reservation.room_id)
    _validate_stay(
        room, check_in_date, check_out_date, num_adults, num_children,
        exclude_id=reservation.id, allow_past_arrival=reservation.status == 'checked_in',
    )
    if reservation.status == 'checked_in' and check_in_date != reservation.check_in_date:
        raise ValidationError('The arrival date cannot change after check-in.')
    from .models import ReservationAmendmentHistory
    from .pricing import calculate_quote
    before = {
        'check_in_date': reservation.check_in_date.isoformat(),
        'check_out_date': reservation.check_out_date.isoformat(),
        'num_adults': reservation.num_adults, 'num_children': reservation.num_children,
        'total_amount': str(reservation.total_amount), 'price_snapshot': reservation.price_snapshot,
    }
    if reservation.rate_plan_id:
        new_snapshot = calculate_quote(
            room=room, rate_plan=reservation.rate_plan, check_in_date=check_in_date,
            check_out_date=check_out_date, num_adults=num_adults, num_children=num_children,
        )
        new_total = Decimal(new_snapshot['total'])
    else:
        nights = (check_out_date - check_in_date).days
        new_total = reservation.nightly_rate * nights
        new_snapshot = {**reservation.price_snapshot, 'nights': nights, 'subtotal': str(new_total), 'total': str(new_total)}
    difference = new_total - reservation.total_amount
    reservation.check_in_date, reservation.check_out_date = check_in_date, check_out_date
    reservation.num_adults, reservation.num_children = num_adults, num_children
    reservation.total_amount, reservation.price_snapshot = new_total, new_snapshot
    reservation.save()
    after = {
        'check_in_date': check_in_date.isoformat(), 'check_out_date': check_out_date.isoformat(),
        'num_adults': num_adults, 'num_children': num_children,
        'total_amount': str(new_total), 'price_snapshot': new_snapshot,
    }
    amendment = ReservationAmendmentHistory.objects.create(
        reservation=reservation, action='stay_amendment', before=before, after=after,
        reason=reason, actor=actor,
    )
    if difference and hasattr(reservation, 'folio'):
        from apps.billing.services import post_folio_entry
        post_folio_entry(
            folio=reservation.folio, direction='debit' if difference > 0 else 'credit',
            entry_type='adjustment' if difference > 0 else 'credit_note',
            description=f'Stay amendment {reservation.reservation_number}', amount=abs(difference),
            actor=actor, external_key=f'reservation-amendment:{amendment.id}',
            metadata={'reason': reason},
        )
    return reservation


@transaction.atomic
def offer_waitlist_entry(*, entry_id, actor, hours=4):
    from .models import WaitlistEntry
    entry = WaitlistEntry.objects.select_for_update().get(pk=entry_id)
    if entry.status != 'waiting':
        raise ValidationError('Only waiting entries can receive an offer.')
    entry.status, entry.offered_at = 'offered', timezone.now()
    entry.offer_expires_at = timezone.now() + timedelta(hours=hours)
    entry.save(update_fields=['status', 'offered_at', 'offer_expires_at'])
    return entry


@transaction.atomic
def convert_waitlist_entry(*, entry_id, room, actor):
    from .models import WaitlistEntry
    entry = WaitlistEntry.objects.select_for_update().select_related('guest', 'room_type').get(pk=entry_id)
    if entry.status != 'offered' or not entry.offer_expires_at or entry.offer_expires_at <= timezone.now():
        if entry.status == 'offered':
            entry.status = 'expired'
            entry.save(update_fields=['status'])
        raise ValidationError('This waitlist offer is not active.')
    if room.room_type_id != entry.room_type_id:
        raise ValidationError('Selected room does not match the requested room type.')
    reservation = create_reservation(
        guest=entry.guest, room=room, check_in_date=entry.check_in_date,
        check_out_date=entry.check_out_date, num_adults=entry.num_adults,
        num_children=entry.num_children, notes=entry.notes, created_by=actor,
        source='front_desk',
    )
    entry.status, entry.converted_reservation = 'converted', reservation
    entry.save(update_fields=['status', 'converted_reservation'])
    return reservation


@transaction.atomic
def request_reservation_discount(*, reservation_id, amount, reason, actor):
    from .models import ReservationDiscountRequest
    reservation = Reservation.objects.select_for_update().get(pk=reservation_id)
    amount = Decimal(str(amount))
    if reservation.status not in {'pending', 'confirmed', 'checked_in'}:
        raise ValidationError('Discounts can only be requested for active stays.')
    if amount <= 0 or amount > reservation.total_amount:
        raise ValidationError('Discount amount must be greater than zero and no more than the stay total.')
    if not reason.strip():
        raise ValidationError('A discount reason is required.')
    return ReservationDiscountRequest.objects.create(
        reservation=reservation, amount=amount, reason=reason.strip(), requested_by=actor,
    )


@transaction.atomic
def review_reservation_discount(*, request_id, action, actor, note=''):
    from apps.billing.services import ensure_folio_for_reservation, post_folio_entry
    from apps.frontend.models import OperationalSetting
    from .models import ReservationDiscountRequest

    discount = ReservationDiscountRequest.objects.select_for_update().select_related('reservation').get(pk=request_id)
    if discount.status != 'pending':
        raise ValidationError('This discount request has already been reviewed.')
    if action not in {'approve', 'reject'}:
        raise ValidationError('Unknown discount review action.')
    if getattr(actor, 'role', None) not in {'admin', 'manager'} and not actor.is_superuser:
        raise ValidationError('Only managers or administrators can review discounts.')
    if actor_id := getattr(actor, 'id', None):
        if actor_id == discount.requested_by_id and getattr(actor, 'role', None) != 'admin' and not actor.is_superuser:
            raise ValidationError('Managers cannot approve their own discount requests.')

    if action == 'approve':
        setting = OperationalSetting.objects.filter(key='discount-approval-limits').first()
        limits = setting.value if setting else {'manager': 20, 'admin': 100}
        role = 'admin' if actor.is_superuser else actor.role
        limit = Decimal(str(limits.get(role, 0)))
        percent = (discount.amount / discount.reservation.total_amount * Decimal('100')).quantize(Decimal('0.01'))
        if percent > limit:
            raise ValidationError(f'{role.title()} discount approval is limited to {limit}%.')
        folio = ensure_folio_for_reservation(discount.reservation, actor=actor)
        post_folio_entry(
            folio=folio, direction='credit', entry_type='credit_note',
            description=f'Approved discount: {discount.reason}', amount=discount.amount,
            actor=actor, external_key=f'reservation-discount:{discount.id}',
            metadata={'approved_percent': str(percent), 'review_note': note},
        )
        discount.status = 'approved'
    else:
        discount.status = 'rejected'
    discount.reviewed_by = actor
    discount.review_note = note
    discount.reviewed_at = timezone.now()
    discount.save(update_fields=['status', 'reviewed_by', 'review_note', 'reviewed_at'])
    return discount
