from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import GuestProfile, UserProfile
from apps.billing.models import Invoice, InvoiceItem
from apps.housekeeping.models import HousekeepingTask
from apps.payments.models import Payment
from apps.reservations.models import Reservation
from apps.rooms.models import Room
from apps.services.models import MenuItem, ServiceOrder, ServiceOrderItem


class Command(BaseCommand):
    help = 'Seed demo operational data for GRACEDAY INN website and portals.'

    def handle(self, *args, **options):
        self.stdout.write('Seeding GRACEDAY INN demo data...')
        call_command('create_initial_data')

        staff = self._ensure_staff_users()
        guests = self._ensure_guests()
        reservations = self._ensure_reservations(staff, guests)
        self._ensure_invoices_and_payments(staff, reservations)
        self._ensure_service_orders(guests)
        self._ensure_housekeeping_tasks(staff)
        self.stdout.write(self.style.SUCCESS('Demo data seeded successfully.'))

    def _ensure_staff_users(self):
        staff_users = {}
        staff_defs = [
            ('manager1', 'manager@gracedayinn.com', 'manager', 'Grace', 'Manager'),
            ('reception1', 'reception@gracedayinn.com', 'receptionist', 'Front', 'Desk'),
            ('housekeeper1', 'housekeeping@gracedayinn.com', 'housekeeping', 'Clean', 'Team'),
        ]
        for username, email, role, first_name, last_name in staff_defs:
            user, created = UserProfile.objects.get_or_create(
                username=username,
                defaults={
                    'email': email,
                    'role': role,
                    'first_name': first_name,
                    'last_name': last_name,
                    'is_active': True,
                },
            )
            if created or not user.has_usable_password():
                user.set_password('demo12345')
                user.save(update_fields=['password'])
            staff_users[role] = user
        return staff_users

    def _ensure_guests(self):
        guests = []
        guest_defs = [
            ('guest_a', 'guesta@example.com', 'Ada', 'Nwosu'),
            ('guest_b', 'guestb@example.com', 'Bola', 'Akin'),
            ('guest_c', 'guestc@example.com', 'Chidi', 'Okafor'),
        ]
        for username, email, first_name, last_name in guest_defs:
            user, created = UserProfile.objects.get_or_create(
                username=username,
                defaults={
                    'email': email,
                    'role': 'guest',
                    'first_name': first_name,
                    'last_name': last_name,
                    'is_active': True,
                },
            )
            if created or not user.has_usable_password():
                user.set_password('demo12345')
                user.save(update_fields=['password'])
            GuestProfile.objects.get_or_create(user=user)
            guests.append(user)
        return guests

    def _ensure_reservations(self, staff, guests):
        if Reservation.objects.exists():
            return list(Reservation.objects.all()[:3])

        today = timezone.localdate()
        rooms = list(Room.objects.filter(is_active=True, status='available').order_by('number')[:3])
        if len(rooms) < 3:
            return []

        reservations = [
            Reservation.objects.create(
                guest=guests[0],
                room=rooms[0],
                check_in_date=today + timedelta(days=1),
                check_out_date=today + timedelta(days=3),
                num_adults=2,
                status='confirmed',
                nightly_rate=rooms[0].current_price,
                created_by=staff['receptionist'],
            ),
            Reservation.objects.create(
                guest=guests[1],
                room=rooms[1],
                check_in_date=today,
                check_out_date=today + timedelta(days=2),
                num_adults=1,
                status='checked_in',
                nightly_rate=rooms[1].current_price,
                created_by=staff['receptionist'],
            ),
            Reservation.objects.create(
                guest=guests[2],
                room=rooms[2],
                check_in_date=today + timedelta(days=2),
                check_out_date=today + timedelta(days=5),
                num_adults=2,
                status='pending',
                nightly_rate=rooms[2].current_price,
                created_by=staff['receptionist'],
            ),
        ]

        rooms[1].status = 'occupied'
        rooms[1].save(update_fields=['status'])
        return reservations

    def _ensure_invoices_and_payments(self, staff, reservations):
        for reservation in reservations:
            invoice, created = Invoice.objects.get_or_create(
                reservation=reservation,
                defaults={
                    'guest': reservation.guest,
                    'status': 'sent',
                    'due_date': reservation.check_in_date,
                },
            )
            if created:
                InvoiceItem.objects.create(
                    invoice=invoice,
                    description=f'Accommodation ({reservation.reservation_number})',
                    quantity=max(reservation.nights, 1),
                    unit_price=reservation.nightly_rate,
                )
                invoice.save()

            if reservation.status in {'confirmed', 'checked_in'} and not invoice.payments.exists():
                Payment.objects.create(
                    invoice=invoice,
                    amount=min(invoice.total, Decimal('50000.00')),
                    method='card',
                    status='completed',
                    transaction_id=f'TXN-{reservation.id}',
                    processed_by=staff['receptionist'],
                )

    def _ensure_service_orders(self, guests):
        menu_item = MenuItem.objects.filter(is_available=True).first()
        room = Room.objects.filter(is_active=True).first()
        if not menu_item or not room or ServiceOrder.objects.exists():
            return

        order = ServiceOrder.objects.create(
            guest=guests[0],
            room=room,
            status='completed',
            notes='Demo room service order',
        )
        ServiceOrderItem.objects.create(order=order, menu_item=menu_item, quantity=2, unit_price=menu_item.price)

    def _ensure_housekeeping_tasks(self, staff):
        room = Room.objects.filter(status='housekeeping').first() or Room.objects.filter(is_active=True).first()
        if not room or HousekeepingTask.objects.exists():
            return

        HousekeepingTask.objects.create(
            room=room,
            task_type='cleaning',
            priority='high',
            status='in_progress',
            assigned_to=staff['housekeeping'],
            notes='Demo housekeeping task',
            created_by=staff['manager'],
            started_at=timezone.now(),
        )
