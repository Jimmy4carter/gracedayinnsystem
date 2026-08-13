from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection
from django.test import TransactionTestCase
from django.utils import timezone
from unittest import skipUnless

from apps.accounts.models import UserProfile
from apps.reservations.models import InventoryHold
from apps.reservations.pricing import create_quote

from .models import RatePlan, Room, RoomType


@skipUnless(connection.vendor == 'postgresql', 'PostgreSQL row-lock contract')
class PostgreSQLInventoryConcurrencyTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        guest = UserProfile.objects.create_user(
            username='concurrent-guest', role='guest', password='test-pass'
        )
        room_type = RoomType.objects.create(
            name='Concurrency Room', base_price='100.00', max_occupancy=2
        )
        room = Room.objects.create(number='CON-1', room_type=room_type)
        self.room_id = room.pk
        self.plan_id = room_type.rate_plans.get().pk
        self.guest_id = guest.pk
        self.arrival = timezone.localdate() + timedelta(days=30)

    def _competing_quote(self, barrier):
        close_old_connections()
        try:
            room = Room.objects.get(pk=self.room_id)
            plan = RatePlan.objects.get(pk=self.plan_id)
            guest = UserProfile.objects.get(pk=self.guest_id)
            barrier.wait(timeout=10)
            quote = create_quote(
                room=room,
                rate_plan=plan,
                check_in_date=self.arrival,
                check_out_date=self.arrival + timedelta(days=2),
                guest=guest,
            )
            return ('created', quote.pk)
        except ValidationError:
            return ('rejected', None)
        finally:
            close_old_connections()

    def test_competing_quotes_create_exactly_one_active_hold(self):
        barrier = Barrier(2)
        with ThreadPoolExecutor(max_workers=2) as executor:
            outcomes = list(executor.map(lambda _: self._competing_quote(barrier), range(2)))

        self.assertCountEqual([status for status, _ in outcomes], ['created', 'rejected'])
        self.assertEqual(
            InventoryHold.objects.filter(room_id=self.room_id, status='active').count(),
            1,
        )
