from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import InventoryBlock, Room


def overlapping_blocks(room, start_date, end_date):
    return InventoryBlock.objects.filter(
        room=room, status='active', start_date__lt=end_date, end_date__gt=start_date,
    )


@transaction.atomic
def create_inventory_block(*, room, start_date, end_date, reason, actor=None,
                           notes='', source_model='', source_id=''):
    locked_room = Room.objects.select_for_update().get(pk=room.pk)
    block = InventoryBlock(
        room=locked_room, start_date=start_date, end_date=end_date, reason=reason,
        notes=notes, source_model=source_model, source_id=str(source_id or ''), created_by=actor,
    )
    block.full_clean()
    if overlapping_blocks(locked_room, start_date, end_date).filter(
        source_model=source_model, source_id=str(source_id or '')
    ).exists():
        raise ValidationError('An equivalent active inventory block already exists.')
    block.save()
    return block


@transaction.atomic
def release_inventory_block(*, block_id, actor=None):
    block = InventoryBlock.objects.select_for_update().get(pk=block_id)
    if block.status == 'released':
        return block
    block.status = 'released'
    block.released_by = actor
    block.released_at = timezone.now()
    block.save(update_fields=['status', 'released_by', 'released_at'])
    return block


def release_source_blocks(*, source_model, source_id, actor=None):
    blocks = InventoryBlock.objects.filter(
        source_model=source_model, source_id=str(source_id), status='active'
    )
    for block in blocks:
        release_inventory_block(block_id=block.id, actor=actor)
    return blocks.count()
