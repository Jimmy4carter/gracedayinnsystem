from django.core.exceptions import ValidationError
from django.db import transaction

from apps.billing.services import ensure_folio_for_reservation, post_folio_entry
from apps.notifications.models import Notification

from .models import MenuItem, ServiceOrder, ServiceOrderItem


@transaction.atomic
def add_service_order_item(*, order_id, menu_item, quantity, actor=None):
    order = ServiceOrder.objects.select_for_update().get(pk=order_id)
    if order.status != 'pending':
        raise ValidationError('Items can only be changed while an order is pending.')
    try:
        quantity = int(quantity)
    except (TypeError, ValueError) as exc:
        raise ValidationError('Quantity must be a positive whole number.') from exc
    if quantity < 1 or quantity > 100:
        raise ValidationError('Quantity must be between 1 and 100.')
    if not menu_item.is_available:
        raise ValidationError('That menu item is unavailable.')
    item = ServiceOrderItem.objects.create(
        order=order, menu_item=menu_item, quantity=quantity, unit_price=menu_item.price,
    )
    return item


@transaction.atomic
def remove_service_order_item(*, order_id, item_id, actor=None):
    order = ServiceOrder.objects.select_for_update().get(pk=order_id)
    if order.status != 'pending':
        raise ValidationError('Items can only be changed while an order is pending.')
    item = ServiceOrderItem.objects.select_for_update().filter(pk=item_id, order=order).first()
    if not item:
        raise ValidationError('Order item was not found in this order.')
    item.delete()
    return order


@transaction.atomic
def transition_service_order(*, order_id, action, actor=None):
    order = ServiceOrder.objects.select_for_update().select_related(
        'guest', 'reservation'
    ).prefetch_related('items').get(pk=order_id)
    transitions = {
        'confirm': ({'pending'}, 'confirmed'),
        'start': ({'confirmed'}, 'in_progress'),
        'complete': ({'in_progress'}, 'completed'),
        'cancel': ({'pending', 'confirmed'}, 'cancelled'),
    }
    if action not in transitions:
        raise ValidationError('Unknown service order action.')
    allowed, target = transitions[action]
    if order.status not in allowed:
        raise ValidationError(f'Cannot move order from {order.status} to {target}.')
    if action == 'complete':
        order.recalculate_total()
        order.refresh_from_db(fields=['total'])
        if order.total <= 0:
            raise ValidationError('A service order must contain a priced item before completion.')
        if order.reservation_id:
            folio = ensure_folio_for_reservation(order.reservation, actor=actor)
            post_folio_entry(
                folio=folio, direction='debit', entry_type='service',
                description=f'Service order {order.order_number}', amount=order.total,
                actor=actor, external_key=f'service-order:{order.id}',
                metadata={'order_number': order.order_number},
            )
    order.status = target
    order.save(update_fields=['status', 'updated_at'])
    Notification.objects.create(
        recipient=order.guest, title='Service order updated',
        message=f'Order {order.order_number} status is now {order.get_status_display()}.',
        notification_type='service', link='/portal/services/',
    )
    return order
