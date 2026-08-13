from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.rooms.models import Room, RoomType

from .models import IncidentReportHistory, LostFoundItemHistory
from .services import (
    create_incident, register_lost_found_item, transition_incident,
    transition_lost_found_item,
)


class OperationalRegisterTests(TestCase):
    def setUp(self):
        room_type = RoomType.objects.create(name='Operations Room', base_price='20000.00')
        self.room = Room.objects.create(number='OPS-1', room_type=room_type)
        self.manager = UserProfile.objects.create_user('ops-manager', password='pass', role='manager')
        self.receptionist = UserProfile.objects.create_user('ops-reception', password='pass', role='receptionist')
        self.housekeeper = UserProfile.objects.create_user('ops-housekeeper', password='pass', role='housekeeping')
        self.guest = UserProfile.objects.create_user('ops-guest', password='pass', role='guest')

    def test_incident_requires_management_resolution_and_retains_immutable_history(self):
        incident = create_incident(
            actor=self.receptionist, incident_type='safety', severity='high',
            title='Wet floor fall', description='Guest slipped near the lobby entrance.',
            location='Lobby', occurred_at=timezone.now(), assigned_to=self.manager,
        )
        transition_incident(
            incident_id=incident.id, action='investigate', actor=self.receptionist,
            notes='CCTV and witness review started.',
        )
        with self.assertRaises(ValidationError):
            transition_incident(
                incident_id=incident.id, action='resolve', actor=self.receptionist,
                notes='Corrective action completed.',
            )
        resolved = transition_incident(
            incident_id=incident.id, action='resolve', actor=self.manager,
            notes='Area dried, signage installed, guest follow-up completed.',
        )
        self.assertEqual(resolved.status, 'resolved')
        closed = transition_incident(
            incident_id=incident.id, action='close', actor=self.manager,
            notes='Management review complete.',
        )
        self.assertEqual(closed.status, 'closed')
        self.assertEqual(closed.history.count(), 4)
        history = IncidentReportHistory.objects.filter(incident=closed).first()
        history.notes = 'tampered'
        with self.assertRaises(ValidationError):
            history.save()

    def test_lost_item_enforces_custody_claim_and_handover_evidence(self):
        item = register_lost_found_item(
            actor=self.housekeeper, item_name='Black wallet',
            description='Leather wallet with identifying cards.', found_location='Room OPS-1',
            found_at=timezone.now(), room=self.room,
        )
        with self.assertRaises(ValidationError):
            transition_lost_found_item(item_id=item.id, action='store', actor=self.housekeeper)
        stored = transition_lost_found_item(
            item_id=item.id, action='store', actor=self.housekeeper,
            storage_location='Front office safe compartment 2',
        )
        self.assertEqual(stored.status, 'stored')
        with self.assertRaises(ValidationError):
            transition_lost_found_item(
                item_id=item.id, action='claim', actor=self.receptionist,
                claimant_name='Ada Guest', claimant_contact='08000000000',
            )
        transition_lost_found_item(
            item_id=item.id, action='claim', actor=self.receptionist,
            claimant_name='Ada Guest', claimant_contact='08000000000',
            claim_verification='Matched two card names and wallet contents.',
        )
        returned = transition_lost_found_item(
            item_id=item.id, action='return', actor=self.receptionist,
            notes='Government ID checked; signed handover retained.',
        )
        self.assertEqual(returned.status, 'returned')
        self.assertEqual(returned.completed_by, self.receptionist)
        self.assertEqual(LostFoundItemHistory.objects.filter(item=item).count(), 4)

    def test_guest_cannot_open_operations_portal_and_housekeeping_does_not_see_claimant_pii(self):
        item = register_lost_found_item(
            actor=self.housekeeper, item_name='Phone', description='Blue phone',
            found_location='Hallway', found_at=timezone.now(),
        )
        transition_lost_found_item(
            item_id=item.id, action='store', actor=self.housekeeper, storage_location='Safe 1',
        )
        transition_lost_found_item(
            item_id=item.id, action='claim', actor=self.receptionist,
            claimant_name='Private Claimant', claimant_contact='private@example.com',
            claim_verification='Unlock code demonstrated.',
        )
        self.client.force_login(self.guest)
        denied = self.client.get(reverse('frontend:portal-operations'))
        self.assertRedirects(denied, reverse('frontend:portal-dashboard'), fetch_redirect_response=False)

        self.client.force_login(self.housekeeper)
        page = self.client.get(reverse('frontend:portal-operations'))
        self.assertEqual(page.status_code, 200)
        self.assertContains(page, 'Phone')
        self.assertNotContains(page, 'Private Claimant')
        self.assertNotContains(page, 'private@example.com')
