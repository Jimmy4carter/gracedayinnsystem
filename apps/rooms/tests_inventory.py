from datetime import timedelta
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.billing.services import ensure_folio_for_reservation
from apps.housekeeping.services import create_maintenance_ticket, transition_maintenance_ticket
from apps.reservations.pricing import convert_quote, create_quote

from .inventory import create_inventory_block
from .models import BookableExtra, InventoryBlock, Room, RoomType, TaxFee


class SellableInventoryAndExtraTests(TestCase):
    def setUp(self):
        self.manager = UserProfile.objects.create_user(
            username='inventory-manager', role='manager', password='test-pass'
        )
        self.guest = UserProfile.objects.create_user(
            username='inventory-guest', role='guest', password='test-pass'
        )
        self.receptionist = UserProfile.objects.create_user(
            username='inventory-reception', role='receptionist', password='test-pass'
        )
        self.room_type = RoomType.objects.create(name='Inventory Room', base_price='100.00', max_occupancy=2)
        self.room = Room.objects.create(number='INV-1', room_type=self.room_type, status='housekeeping')
        self.plan = self.room_type.rate_plans.get()
        self.arrival = timezone.localdate() + timedelta(days=10)

    def test_current_operational_state_does_not_replace_date_bound_sales_inventory(self):
        quote = create_quote(
            room=self.room, rate_plan=self.plan, check_in_date=self.arrival,
            check_out_date=self.arrival + timedelta(days=2), guest=self.guest,
        )
        self.assertEqual(quote.status, 'active')
        quote.hold.status = 'released'
        quote.hold.save(update_fields=['status'])
        quote.status = 'cancelled'
        quote.save(update_fields=['status'])
        create_inventory_block(
            room=self.room, start_date=self.arrival, end_date=self.arrival + timedelta(days=2),
            reason='owner_use', actor=self.manager,
        )
        with self.assertRaises(ValidationError):
            create_quote(
                room=self.room, rate_plan=self.plan, check_in_date=self.arrival,
                check_out_date=self.arrival + timedelta(days=2), guest=self.guest,
            )

    def test_maintenance_creates_and_releases_sales_block(self):
        ticket = create_maintenance_ticket(
            room=self.room, title='Air conditioner', description='Repair required',
            actor=self.manager, downtime_required=True,
        )
        self.assertTrue(InventoryBlock.objects.filter(
            source_model='MaintenanceTicket', source_id=str(ticket.id), status='active'
        ).exists())
        transition_maintenance_ticket(ticket_id=ticket.id, action='start', actor=self.manager)
        transition_maintenance_ticket(ticket_id=ticket.id, action='resolve', actor=self.manager)
        transition_maintenance_ticket(ticket_id=ticket.id, action='approve', actor=self.manager)
        self.assertFalse(InventoryBlock.objects.filter(
            source_model='MaintenanceTicket', source_id=str(ticket.id), status='active'
        ).exists())

    def test_manager_controls_sales_blocks_in_room_portal(self):
        self.client.force_login(self.manager)
        response = self.client.post(reverse('frontend:portal-rooms'), {
            'command': 'create_inventory_block', 'room_id': self.room.id,
            'start_date': self.arrival.isoformat(),
            'end_date': (self.arrival + timedelta(days=2)).isoformat(),
            'reason': 'owner_use', 'notes': 'Management hold',
        })
        self.assertRedirects(response, reverse('frontend:portal-rooms'))
        block = InventoryBlock.objects.get(room=self.room, status='active')
        response = self.client.post(reverse('frontend:portal-rooms'), {
            'command': 'release_inventory_block', 'block_id': block.id,
        })
        self.assertRedirects(response, reverse('frontend:portal-rooms'))
        block.refresh_from_db()
        self.assertEqual(block.status, 'released')

    def test_receptionist_cannot_create_sales_block(self):
        self.client.force_login(self.receptionist)
        self.client.post(reverse('frontend:portal-rooms'), {
            'command': 'create_inventory_block', 'room_id': self.room.id,
            'start_date': self.arrival.isoformat(),
            'end_date': (self.arrival + timedelta(days=2)).isoformat(),
            'reason': 'owner_use',
        })
        self.assertFalse(InventoryBlock.objects.exists())

    def test_taxable_extras_are_snapshotted_and_posted_to_folio(self):
        extra = BookableExtra.objects.create(
            code='breakfast', name='Breakfast', pricing_model='per_night',
            amount='50.00', taxable=True,
        )
        extra.room_types.add(self.room_type)
        TaxFee.objects.create(
            name='VAT', code='vat-extra', calculation='percentage', amount='10.00'
        )
        quote = create_quote(
            room=self.room, rate_plan=self.plan, check_in_date=self.arrival,
            check_out_date=self.arrival + timedelta(days=2), guest=self.guest, extras=[extra],
        )
        self.assertEqual(quote.subtotal, Decimal('200.00'))
        self.assertEqual(quote.extra_total, Decimal('100.00'))
        self.assertEqual(quote.tax_total, Decimal('30.00'))
        self.assertEqual(quote.total, Decimal('330.00'))
        reservation = convert_quote(quote_id=quote.id, guest=self.guest, created_by=self.manager)
        folio = ensure_folio_for_reservation(reservation, actor=self.manager)
        self.assertEqual(folio.balance, Decimal('330.00'))
        self.assertTrue(folio.entries.filter(entry_type='service', description='Breakfast').exists())

    def test_occupant_supplements_are_disclosed_taxed_and_snapshotted(self):
        self.plan.included_adults = 1
        self.plan.extra_adult_per_night = Decimal('20.00')
        self.plan.child_per_night = Decimal('10.00')
        self.plan.save()
        TaxFee.objects.create(
            name='VAT', code='vat-occupants', calculation='percentage', amount='10.00'
        )
        quote = create_quote(
            room=self.room, rate_plan=self.plan, check_in_date=self.arrival,
            check_out_date=self.arrival + timedelta(days=2), guest=self.guest,
            num_adults=1, num_children=1,
        )
        self.assertEqual(quote.subtotal, Decimal('220.00'))
        self.assertEqual(quote.tax_total, Decimal('22.00'))
        self.assertEqual(quote.total, Decimal('242.00'))
        self.assertEqual(quote.price_snapshot['occupant_supplement_total'], '20.00')
        self.assertEqual(quote.policy_snapshot['child_per_night'], '10.00')
