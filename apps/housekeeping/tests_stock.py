import uuid

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import UserProfile

from .models import StockBalance, StockItem, StockLocation, StockMovement
from .services import record_stock_movement, transfer_stock


class OperationalStockTests(TestCase):
    def setUp(self):
        self.manager = UserProfile.objects.create_user('stock-manager', password='pass', role='manager')
        self.housekeeper = UserProfile.objects.create_user('stock-housekeeper', password='pass', role='housekeeping')
        self.receptionist = UserProfile.objects.create_user('stock-reception', password='pass', role='receptionist')
        self.main = StockLocation.objects.create(code='main', name='Main Store', location_type='main_store')
        self.floor = StockLocation.objects.create(code='floor-1', name='Floor 1 Store', location_type='floor_store')
        self.linen = StockItem.objects.create(
            sku='bath-towel', name='Bath towel', category='linen', unit='each', reorder_level=5,
        )
        self.minibar = StockItem.objects.create(
            sku='water-50cl', name='Water 50cl', category='minibar', unit='bottle', reorder_level=12,
        )

    def test_movements_are_idempotent_append_only_and_cannot_overdraw(self):
        key = uuid.uuid4()
        first = record_stock_movement(
            item=self.linen, location=self.main, movement_type='receipt', quantity=20,
            reason='Opening verified count', actor=self.manager, idempotency_key=key,
        )
        replay = record_stock_movement(
            item=self.linen, location=self.main, movement_type='receipt', quantity=20,
            reason='Opening verified count', actor=self.manager, idempotency_key=key,
        )
        self.assertEqual(first.pk, replay.pk)
        self.assertEqual(StockMovement.objects.count(), 1)
        with self.assertRaisesMessage(ValidationError, 'different stock movement'):
            record_stock_movement(
                item=self.linen, location=self.main, movement_type='receipt', quantity=19,
                reason='Opening verified count', actor=self.manager, idempotency_key=key,
            )
        with self.assertRaises(ValidationError):
            record_stock_movement(
                item=self.linen, location=self.main, movement_type='issue', quantity=21,
                reason='Impossible issue', actor=self.housekeeper,
            )
        self.assertEqual(StockBalance.objects.get(item=self.linen, location=self.main).quantity, 20)
        first.reason = 'tampered'
        with self.assertRaises(ValidationError):
            first.save()

    def test_transfer_posts_balanced_pair_and_replay_does_not_duplicate(self):
        record_stock_movement(
            item=self.linen, location=self.main, movement_type='receipt', quantity=30,
            reason='Supplier delivery', actor=self.manager,
        )
        key = uuid.uuid4()
        movements = transfer_stock(
            item=self.linen, source=self.main, destination=self.floor, quantity=8,
            reason='Floor par replenishment', actor=self.housekeeper, idempotency_key=key,
        )
        replay = transfer_stock(
            item=self.linen, source=self.main, destination=self.floor, quantity=8,
            reason='Floor par replenishment', actor=self.housekeeper, idempotency_key=key,
        )
        self.assertEqual(len(movements), 2)
        self.assertEqual([item.pk for item in replay], [item.pk for item in movements])
        self.assertEqual(StockBalance.objects.get(item=self.linen, location=self.main).quantity, 22)
        self.assertEqual(StockBalance.objects.get(item=self.linen, location=self.floor).quantity, 8)
        self.assertEqual(sum(item.quantity_delta for item in movements), 0)

    def test_role_category_and_receipt_boundaries_are_enforced(self):
        with self.assertRaises(ValidationError):
            record_stock_movement(
                item=self.linen, location=self.main, movement_type='receipt', quantity=5,
                reason='Unauthorized receipt', actor=self.housekeeper,
            )
        with self.assertRaises(ValidationError):
            record_stock_movement(
                item=self.linen, location=self.main, movement_type='issue', quantity=1,
                reason='Wrong department', actor=self.receptionist,
            )

    def test_portal_scopes_categories_by_operational_role(self):
        record_stock_movement(
            item=self.linen, location=self.main, movement_type='receipt', quantity=10,
            reason='Linen delivery', actor=self.manager,
        )
        record_stock_movement(
            item=self.minibar, location=self.main, movement_type='receipt', quantity=10,
            reason='Minibar delivery', actor=self.manager,
        )
        self.client.force_login(self.housekeeper)
        response = self.client.get(reverse('frontend:portal-stock'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Bath towel')
        self.assertNotContains(response, 'Water 50cl')
