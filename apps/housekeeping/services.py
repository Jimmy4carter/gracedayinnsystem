from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from datetime import date
from decimal import Decimal, InvalidOperation
import uuid

from apps.rooms.models import Room

from .models import (
    HousekeepingTask, HousekeepingTaskHistory, IncidentReport, IncidentReportHistory,
    LostFoundItem, LostFoundItemHistory, MaintenanceTicket, MaintenanceTicketHistory,
    StockBalance, StockItem, StockLocation, StockMovement,
)


@transaction.atomic
def create_housekeeping_task(*, room, task_type='cleaning', priority='medium', assigned_to=None,
                             notes='', scheduled_at=None, actor=None):
    task = HousekeepingTask.objects.create(
        room=room, task_type=task_type, priority=priority, assigned_to=assigned_to,
        notes=notes, scheduled_at=scheduled_at, created_by=actor,
    )
    HousekeepingTaskHistory.objects.create(
        task=task, from_status='', to_status='pending', action='create', actor=actor,
    )
    return task


@transaction.atomic
def transition_housekeeping_task(*, task_id, action, actor, notes=''):
    task = HousekeepingTask.objects.select_for_update().select_related('room', 'assigned_to').get(pk=task_id)
    room = Room.objects.select_for_update().get(pk=task.room_id)
    rules = {
        'start': ({'pending'}, 'in_progress'),
        'complete': ({'in_progress'}, 'completed'),
        'verify': ({'completed'}, 'verified'),
        'reopen': ({'completed', 'verified'}, 'in_progress'),
    }
    if action not in rules:
        raise ValidationError('Unknown housekeeping action.')
    allowed, target = rules[action]
    if task.status not in allowed:
        raise ValidationError(f'Cannot move housekeeping task from {task.status} to {target}.')
    if action in {'start', 'complete'} and task.assigned_to_id and actor != task.assigned_to and not (
        actor.is_superuser or actor.role in {'admin', 'manager', 'receptionist'}
    ):
        raise ValidationError('Only the assigned housekeeper or an operational manager can update this task.')
    if action == 'verify' and not (actor.is_superuser or actor.role in {'admin', 'manager', 'receptionist'}):
        raise ValidationError('A supervisor must inspect and verify room readiness.')
    previous = task.status
    now = timezone.now()
    if action == 'start':
        task.started_at = task.started_at or now
        if room.status == 'available':
            room.status = 'housekeeping'
            room.save(update_fields=['status'])
    elif action == 'complete':
        task.completed_at = now
        task.completion_notes = notes
    elif action == 'verify':
        open_downtime = room.maintenance_tickets.filter(
            downtime_required=True, status__in=['reported', 'in_progress', 'resolved']
        ).exists()
        occupied = room.reservations.filter(status='checked_in').exists()
        if open_downtime:
            raise ValidationError('Room cannot be released while a downtime ticket is open.')
        task.verified_at, task.verified_by, task.inspection_notes = now, actor, notes
        if not occupied:
            room.status = 'available'
            room.save(update_fields=['status'])
    elif action == 'reopen':
        task.verified_at = None
        task.verified_by = None
        task.inspection_notes = notes
        room.status = 'housekeeping'
        room.save(update_fields=['status'])
    task.status = target
    task.save()
    HousekeepingTaskHistory.objects.create(
        task=task, from_status=previous, to_status=target, action=action, actor=actor, notes=notes,
    )
    return task


@transaction.atomic
def create_maintenance_ticket(*, room, title, description, actor, category='general',
                              priority='medium', downtime_required=True, assigned_to=None,
                              estimated_cost=0, evidence=None):
    locked_room = Room.objects.select_for_update().get(pk=room.pk)
    ticket = MaintenanceTicket.objects.create(
        room=locked_room, title=title, description=description, category=category,
        priority=priority, downtime_required=downtime_required, assigned_to=assigned_to,
        reported_by=actor, estimated_cost=estimated_cost or 0, evidence=evidence,
    )
    if downtime_required:
        locked_room.status = 'out_of_order' if priority == 'urgent' else 'maintenance'
        locked_room.save(update_fields=['status'])
        from apps.rooms.inventory import create_inventory_block
        create_inventory_block(
            room=locked_room, start_date=timezone.localdate(), end_date=date(2100, 1, 1),
            reason='maintenance', actor=actor, notes=f'Maintenance ticket {ticket.reference}',
            source_model='MaintenanceTicket', source_id=ticket.id,
        )
    MaintenanceTicketHistory.objects.create(
        ticket=ticket, from_status='', to_status='reported', action='report', actor=actor,
    )
    return ticket


@transaction.atomic
def transition_maintenance_ticket(*, ticket_id, action, actor, notes='', actual_cost=None):
    ticket = MaintenanceTicket.objects.select_for_update().select_related('room').get(pk=ticket_id)
    room = Room.objects.select_for_update().get(pk=ticket.room_id)
    rules = {
        'start': ({'reported'}, 'in_progress'),
        'resolve': ({'in_progress'}, 'resolved'),
        'approve': ({'resolved'}, 'approved'),
        'cancel': ({'reported'}, 'cancelled'),
        'reopen': ({'resolved', 'approved'}, 'in_progress'),
    }
    if action not in rules:
        raise ValidationError('Unknown maintenance action.')
    allowed, target = rules[action]
    if ticket.status not in allowed:
        raise ValidationError(f'Cannot move maintenance ticket from {ticket.status} to {target}.')
    if action == 'approve' and not (actor.is_superuser or actor.role in {'admin', 'manager'}):
        raise ValidationError('Only management can approve return to service.')
    previous, now = ticket.status, timezone.now()
    if action == 'start':
        ticket.started_at = ticket.started_at or now
    elif action == 'resolve':
        ticket.resolved_at, ticket.resolution_notes = now, notes
        if actual_cost is not None:
            ticket.actual_cost = actual_cost
    elif action == 'approve':
        ticket.approved_at, ticket.approved_by = now, actor
        other_downtime = room.maintenance_tickets.filter(
            downtime_required=True, status__in=['reported', 'in_progress', 'resolved']
        ).exclude(pk=ticket.pk).exists()
        if not other_downtime and not room.reservations.filter(status='checked_in').exists():
            room.status = 'housekeeping'
            room.save(update_fields=['status'])
            create_housekeeping_task(
                room=room, task_type='inspection', priority='high', actor=actor,
                notes=f'Return-to-service inspection after maintenance {ticket.reference}.',
            )
        from apps.rooms.inventory import release_source_blocks
        release_source_blocks(source_model='MaintenanceTicket', source_id=ticket.id, actor=actor)
    elif action == 'reopen':
        ticket.approved_at = None
        ticket.approved_by = None
        room.status = 'maintenance'
        room.save(update_fields=['status'])
        if ticket.downtime_required and not room.inventory_blocks.filter(
            status='active', source_model='MaintenanceTicket', source_id=str(ticket.id)
        ).exists():
            from apps.rooms.inventory import create_inventory_block
            create_inventory_block(
                room=room, start_date=timezone.localdate(), end_date=date(2100, 1, 1),
                reason='maintenance', actor=actor, notes=f'Reopened maintenance {ticket.reference}',
                source_model='MaintenanceTicket', source_id=ticket.id,
            )
    elif action == 'cancel' and ticket.downtime_required:
        room.status = 'housekeeping'
        room.save(update_fields=['status'])
        from apps.rooms.inventory import release_source_blocks
        release_source_blocks(source_model='MaintenanceTicket', source_id=ticket.id, actor=actor)
    ticket.status = target
    ticket.save()
    MaintenanceTicketHistory.objects.create(
        ticket=ticket, from_status=previous, to_status=target, action=action,
        actor=actor, notes=notes,
    )
    return ticket


@transaction.atomic
def create_incident(*, actor, incident_type, severity, title, description, location,
                    occurred_at, room=None, reservation=None, assigned_to=None):
    if severity == 'critical' and not assigned_to:
        assigned_to = actor if actor.role in {'admin', 'manager'} else None
    incident = IncidentReport.objects.create(
        incident_type=incident_type, severity=severity, title=title.strip(),
        description=description.strip(), location=location.strip(), occurred_at=occurred_at,
        room=room, reservation=reservation, reported_by=actor, assigned_to=assigned_to,
    )
    IncidentReportHistory.objects.create(
        incident=incident, from_status='', to_status='open', action='report', actor=actor,
    )
    return incident


@transaction.atomic
def transition_incident(*, incident_id, action, actor, notes=''):
    incident = IncidentReport.objects.select_for_update().get(pk=incident_id)
    rules = {
        'investigate': ({'open'}, 'investigating'),
        'resolve': ({'open', 'investigating'}, 'resolved'),
        'close': ({'resolved'}, 'closed'),
        'reopen': ({'resolved', 'closed'}, 'investigating'),
    }
    if action not in rules:
        raise ValidationError('Unknown incident action.')
    allowed, target = rules[action]
    if incident.status not in allowed:
        raise ValidationError(f'Cannot move incident from {incident.status} to {target}.')
    if action in {'resolve', 'close', 'reopen'} and not (
        actor.is_superuser or actor.role in {'admin', 'manager'}
    ):
        raise ValidationError('Only management can resolve, close, or reopen an incident.')
    if action in {'resolve', 'close'} and not notes.strip():
        raise ValidationError('Resolution or closure notes are required.')
    previous = incident.status
    now = timezone.now()
    if action == 'resolve':
        incident.resolution = notes.strip()
        incident.resolved_at = now
    elif action == 'close':
        incident.closed_at = now
    elif action == 'reopen':
        incident.closed_at = None
        incident.resolved_at = None
    incident.status = target
    incident.save()
    IncidentReportHistory.objects.create(
        incident=incident, from_status=previous, to_status=target,
        action=action, actor=actor, notes=notes.strip(),
    )
    return incident


@transaction.atomic
def register_lost_found_item(*, actor, item_name, description, found_location,
                             found_at, room=None):
    item = LostFoundItem.objects.create(
        item_name=item_name.strip(), description=description.strip(),
        found_location=found_location.strip(), found_at=found_at, room=room, found_by=actor,
    )
    LostFoundItemHistory.objects.create(
        item=item, from_status='', to_status='found', action='register', actor=actor,
    )
    return item


@transaction.atomic
def transition_lost_found_item(*, item_id, action, actor, notes='', storage_location='',
                               claimant_name='', claimant_contact='', claim_verification=''):
    item = LostFoundItem.objects.select_for_update().get(pk=item_id)
    rules = {
        'store': ({'found'}, 'stored'),
        'claim': ({'stored'}, 'claimed'),
        'return': ({'claimed'}, 'returned'),
        'dispose': ({'stored'}, 'disposed'),
        'reopen': ({'claimed'}, 'stored'),
    }
    if action not in rules:
        raise ValidationError('Unknown lost-and-found action.')
    allowed, target = rules[action]
    if item.status not in allowed:
        raise ValidationError(f'Cannot move item from {item.status} to {target}.')
    if action == 'store' and not storage_location.strip():
        raise ValidationError('A secure storage location is required.')
    if action == 'claim' and not all([
        claimant_name.strip(), claimant_contact.strip(), claim_verification.strip(),
    ]):
        raise ValidationError('Claimant identity, contact, and verification evidence are required.')
    if action in {'return', 'dispose'} and not notes.strip():
        raise ValidationError('Disposition notes are required.')
    if action == 'dispose' and not (actor.is_superuser or actor.role in {'admin', 'manager'}):
        raise ValidationError('Only management can authorize disposal.')
    previous = item.status
    if action == 'store':
        item.storage_location = storage_location.strip()
    elif action == 'claim':
        item.claimant_name = claimant_name.strip()
        item.claimant_contact = claimant_contact.strip()
        item.claim_verification = claim_verification.strip()
    elif action in {'return', 'dispose'}:
        item.disposition_notes = notes.strip()
        item.completed_at = timezone.now()
        item.completed_by = actor
    elif action == 'reopen':
        item.claimant_name = item.claimant_contact = item.claim_verification = ''
    item.status = target
    item.save()
    LostFoundItemHistory.objects.create(
        item=item, from_status=previous, to_status=target,
        action=action, actor=actor, notes=notes.strip(),
    )
    return item


def _stock_quantity(value):
    try:
        quantity = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError('Stock quantity must be numeric.') from exc
    if not quantity.is_finite() or quantity <= 0:
        raise ValidationError('Stock quantity must be greater than zero.')
    return quantity.quantize(Decimal('0.001'))


def _authorize_stock(actor, item, movement_type):
    if actor.is_superuser or actor.role in {'admin', 'manager'}:
        return
    if movement_type not in {'issue', 'waste', 'transfer_in', 'transfer_out'}:
        raise ValidationError('Only management can receive or adjust stock.')
    categories = {
        'housekeeping': {'linen', 'housekeeping'},
        'receptionist': {'minibar', 'other'},
    }.get(actor.role, set())
    if item.category not in categories:
        raise ValidationError('This stock category is outside your operational role.')


def _post_stock_delta(*, item, location, movement_type, delta, actor, reason,
                      reference=None, transfer_reference=None):
    StockItem.objects.select_for_update().get(pk=item.pk)
    StockLocation.objects.select_for_update().get(pk=location.pk)
    balance, _created = StockBalance.objects.select_for_update().get_or_create(
        item=item, location=location, defaults={'quantity': 0},
    )
    resulting = balance.quantity + delta
    if resulting < 0:
        raise ValidationError(
            f'Insufficient stock at {location.name}; available balance is {balance.quantity} {item.unit}.'
        )
    balance.quantity = resulting
    balance.save(update_fields=['quantity', 'updated_at'])
    return StockMovement.objects.create(
        reference=reference or uuid.uuid4(), item=item, location=location,
        movement_type=movement_type, quantity_delta=delta,
        resulting_balance=resulting, transfer_reference=transfer_reference,
        reason=reason.strip(), actor=actor,
    )


@transaction.atomic
def record_stock_movement(*, item, location, movement_type, quantity, reason, actor,
                          idempotency_key=None):
    if movement_type not in {'receipt', 'issue', 'waste', 'adjustment_add', 'adjustment_remove'}:
        raise ValidationError('Use the transfer command for location transfers.')
    if not reason.strip():
        raise ValidationError('A stock movement reason is required.')
    if not item.is_active or not location.is_active:
        raise ValidationError('Stock item and location must both be active.')
    _authorize_stock(actor, item, movement_type)
    amount = _stock_quantity(quantity)
    try:
        reference = uuid.UUID(str(idempotency_key)) if idempotency_key else uuid.uuid4()
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError('Stock idempotency key must be a valid UUID.') from exc
    existing = StockMovement.objects.filter(reference=reference).first()
    if existing:
        expected_delta = amount if movement_type in {'receipt', 'adjustment_add'} else -amount
        if not (
            existing.item_id == item.id and existing.location_id == location.id
            and existing.movement_type == movement_type
            and existing.quantity_delta == expected_delta and existing.reason == reason.strip()
        ):
            raise ValidationError('This idempotency key was already used for a different stock movement.')
        return existing
    delta = amount if movement_type in {'receipt', 'adjustment_add'} else -amount
    return _post_stock_delta(
        item=item, location=location, movement_type=movement_type, delta=delta,
        actor=actor, reason=reason, reference=reference,
    )


@transaction.atomic
def transfer_stock(*, item, source, destination, quantity, reason, actor,
                   idempotency_key=None):
    if source.pk == destination.pk:
        raise ValidationError('Source and destination locations must differ.')
    if not reason.strip():
        raise ValidationError('A transfer reason is required.')
    if not item.is_active or not source.is_active or not destination.is_active:
        raise ValidationError('Stock item and locations must be active.')
    _authorize_stock(actor, item, 'transfer_out')
    amount = _stock_quantity(quantity)
    try:
        transfer_reference = uuid.UUID(str(idempotency_key)) if idempotency_key else uuid.uuid4()
    except (ValueError, TypeError, AttributeError) as exc:
        raise ValidationError('Transfer idempotency key must be a valid UUID.') from exc
    existing = list(StockMovement.objects.filter(transfer_reference=transfer_reference).order_by('id'))
    if existing:
        if len(existing) != 2 or not (
            existing[0].item_id == item.id and existing[1].item_id == item.id
            and {existing[0].location_id, existing[1].location_id} == {source.id, destination.id}
            and {existing[0].quantity_delta, existing[1].quantity_delta} == {-amount, amount}
            and all(movement.reason == reason.strip() for movement in existing)
        ):
            raise ValidationError('This idempotency key was already used for a different stock transfer.')
        return existing
    # Lock locations in a stable order to reduce transfer deadlock risk.
    list(StockLocation.objects.select_for_update().filter(pk__in=[source.pk, destination.pk]).order_by('pk'))
    outgoing = _post_stock_delta(
        item=item, location=source, movement_type='transfer_out', delta=-amount,
        actor=actor, reason=reason, transfer_reference=transfer_reference,
    )
    incoming = _post_stock_delta(
        item=item, location=destination, movement_type='transfer_in', delta=amount,
        actor=actor, reason=reason, transfer_reference=transfer_reference,
    )
    return [outgoing, incoming]
