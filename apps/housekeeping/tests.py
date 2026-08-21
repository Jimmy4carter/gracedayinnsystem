from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.accounts.models import UserProfile
from apps.rooms.models import Room, RoomType

from .models import HousekeepingTask, HousekeepingTaskHistory, MaintenanceTicketHistory
from .services import (
    create_housekeeping_task, create_maintenance_ticket, transition_housekeeping_task,
    transition_maintenance_ticket,
)


class OperationsWorkflowTests(TestCase):
    def setUp(self):
        self.manager = UserProfile.objects.create_user(
            username='ops-manager', role='manager', password='test-pass'
        )
        self.receptionist = UserProfile.objects.create_user(
            username='ops-reception', role='receptionist', password='test-pass'
        )
        self.housekeeper = UserProfile.objects.create_user(
            username='ops-housekeeper', role='housekeeping', password='test-pass'
        )
        room_type = RoomType.objects.create(name='Operations Room', base_price='15000.00')
        self.room = Room.objects.create(number='OPS-1', room_type=room_type, status='housekeeping')

    def test_cleaning_requires_supervisor_inspection_before_room_release(self):
        task = create_housekeeping_task(
            room=self.room, assigned_to=self.housekeeper, actor=self.receptionist
        )
        transition_housekeeping_task(task_id=task.id, action='start', actor=self.housekeeper)
        completed = transition_housekeeping_task(
            task_id=task.id, action='complete', actor=self.housekeeper, notes='Cleaned and stocked'
        )
        self.room.refresh_from_db()
        self.assertEqual(completed.status, 'completed')
        self.assertEqual(self.room.status, 'housekeeping')
        with self.assertRaises(ValidationError):
            transition_housekeeping_task(task_id=task.id, action='verify', actor=self.housekeeper)
        verified = transition_housekeeping_task(
            task_id=task.id, action='verify', actor=self.receptionist, notes='Inspection passed'
        )
        self.room.refresh_from_db()
        self.assertEqual(verified.status, 'verified')
        self.assertEqual(verified.verified_by, self.receptionist)
        self.assertEqual(self.room.status, 'available')
        self.assertEqual(task.history.count(), 4)

    def test_open_maintenance_downtime_blocks_housekeeping_release(self):
        ticket = create_maintenance_ticket(
            room=self.room, title='Air conditioner fault', description='Not cooling',
            actor=self.housekeeper, priority='urgent', downtime_required=True,
        )
        self.room.refresh_from_db()
        self.assertEqual(self.room.status, 'out_of_order')
        task = create_housekeeping_task(room=self.room, assigned_to=self.housekeeper, actor=self.manager)
        transition_housekeeping_task(task_id=task.id, action='start', actor=self.housekeeper)
        transition_housekeeping_task(task_id=task.id, action='complete', actor=self.housekeeper)
        with self.assertRaises(ValidationError):
            transition_housekeeping_task(task_id=task.id, action='verify', actor=self.manager)
        transition_maintenance_ticket(ticket_id=ticket.id, action='start', actor=self.housekeeper)
        transition_maintenance_ticket(
            ticket_id=ticket.id, action='resolve', actor=self.housekeeper,
            notes='Compressor replaced', actual_cost='25000.00',
        )
        with self.assertRaises(ValidationError):
            transition_maintenance_ticket(ticket_id=ticket.id, action='approve', actor=self.housekeeper)
        approved = transition_maintenance_ticket(
            ticket_id=ticket.id, action='approve', actor=self.manager
        )
        self.room.refresh_from_db()
        self.assertEqual(approved.status, 'approved')
        self.assertEqual(approved.approved_by, self.manager)
        self.assertEqual(self.room.status, 'housekeeping')
        self.assertTrue(HousekeepingTask.objects.filter(room=self.room, task_type='inspection').exists())

    def test_operational_histories_are_immutable(self):
        task = create_housekeeping_task(room=self.room, actor=self.manager)
        task_history = task.history.get()
        task_history.notes = 'tamper'
        with self.assertRaises(ValidationError):
            task_history.save()
        with self.assertRaises(ValidationError):
            task_history.delete()
        ticket = create_maintenance_ticket(
            room=self.room, title='Lamp', description='Broken lamp', actor=self.manager
        )
        ticket_history = ticket.history.get()
        with self.assertRaises(ValidationError):
            ticket_history.delete()
