from datetime import timedelta
from decimal import Decimal
import tempfile

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.billing.models import Folio, FolioEntry
from apps.reservations.models import Reservation
from apps.rooms.models import Room, RoomType
from apps.notifications.models import InquiryCase, OutboundMessage

from .management_queries import create_management_query, transition_management_query
from .models import DailyMetricSnapshot, ManagementQueryHistory, NightAuditRun
from .reporting import (
    calculate_booking_pace, calculate_daily_metrics, calculate_management_exceptions,
    generate_management_pack, run_night_audit,
)


class ManagementIntelligenceTests(TestCase):
    def setUp(self):
        self.manager = UserProfile.objects.create_user(
            username='metrics-manager', role='manager', password='test-pass'
        )
        self.guest = UserProfile.objects.create_user(
            username='metrics-guest', role='guest', password='test-pass'
        )
        room_type = RoomType.objects.create(name='Metric Room', base_price='10000.00')
        self.room = Room.objects.create(number='MET-1', room_type=room_type)
        self.business_date = timezone.localdate() - timedelta(days=1)
        self.reservation = Reservation.objects.create(
            guest=self.guest, room=self.room, check_in_date=self.business_date,
            check_out_date=self.business_date + timedelta(days=1),
            nightly_rate='10000.00', status='checked_out', created_by=self.manager,
            actual_check_in=timezone.now() - timedelta(days=1), actual_check_out=timezone.now(),
        )
        self.folio = Folio.objects.create(reservation=self.reservation, guest=self.guest)
        room_charge = FolioEntry.objects.create(
            folio=self.folio, direction='debit', entry_type='accommodation',
            description='Room revenue', amount=Decimal('10000.00'), external_key='metric-room',
        )
        service_charge = FolioEntry.objects.create(
            folio=self.folio, direction='debit', entry_type='service',
            description='Service revenue', amount=Decimal('2000.00'), external_key='metric-service',
        )
        posted = timezone.now() - timedelta(days=1)
        FolioEntry.objects.filter(pk__in=[room_charge.pk, service_charge.pk]).update(posted_at=posted)

    def test_metric_formulas_reconcile_to_source_ledgers(self):
        metrics = calculate_daily_metrics(self.business_date)
        self.assertEqual(metrics['available_rooms'], 1)
        self.assertEqual(metrics['occupied_rooms'], 1)
        self.assertEqual(metrics['occupancy_percent'], Decimal('100.00'))
        self.assertEqual(metrics['room_revenue'], Decimal('10000.00'))
        self.assertEqual(metrics['total_revenue'], Decimal('12000.00'))
        self.assertEqual(metrics['adr'], Decimal('10000.00'))
        self.assertEqual(metrics['revpar'], Decimal('10000.00'))
        self.assertEqual(metrics['receivables'], Decimal('12000.00'))

    def test_night_audit_is_one_time_and_snapshot_is_immutable(self):
        audit = run_night_audit(business_date=self.business_date, actor=self.manager)
        self.assertEqual(audit.snapshot.total_revenue, Decimal('12000.00'))
        with self.assertRaises(ValidationError):
            run_night_audit(business_date=self.business_date, actor=self.manager)
        audit.snapshot.total_revenue = Decimal('0.00')
        with self.assertRaises(ValidationError):
            audit.snapshot.save()

    def test_management_query_tracks_assignment_sla_and_resolution(self):
        query = create_management_query(
            title='Revenue variance', description='Investigate ledger variance',
            actor=self.manager, priority='urgent', source_model='DailyMetricSnapshot',
            source_id='2026-08-09',
        )
        self.assertIsNotNone(query.due_at)
        query = transition_management_query(
            query_id=query.id, action='assign', actor=self.manager
        )
        transition_management_query(query_id=query.id, action='investigate', actor=self.manager)
        query = transition_management_query(
            query_id=query.id, action='resolve', actor=self.manager,
            resolution='Reconciled to service folio entry.',
        )
        self.assertEqual(query.status, 'resolved')
        self.assertEqual(query.history.count(), 4)

    def test_booking_pace_and_exception_catalog_are_source_driven(self):
        future_room = Room.objects.create(number='MET-2', room_type=self.room.room_type)
        future = Reservation.objects.create(
            guest=self.guest, room=future_room,
            check_in_date=timezone.localdate() + timedelta(days=10),
            check_out_date=timezone.localdate() + timedelta(days=12),
            nightly_rate='10000.00', status='confirmed', created_by=self.manager,
        )
        Reservation.objects.filter(pk=future.pk).update(created_at=timezone.now() - timedelta(days=2))
        pace = calculate_booking_pace()
        self.assertEqual(pace['current_bookings'], 1)
        self.assertEqual(pace['change'], 1)

        OutboundMessage.objects.create(
            purpose='test', recipient_email='failed@example.com', subject='Failed',
            html_body='Failed', status='failed', idempotency_key='failed-manager-exception',
        )
        exceptions = calculate_management_exceptions()
        self.assertEqual(exceptions['communication_failures'], 1)

    def test_inquiry_detail_portal_renders_and_no_longer_falls_through(self):
        case = InquiryCase.objects.create(
            subject='Portal regression', requester_name='Guest',
            requester_email='guest@example.com', requester=self.guest,
        )
        self.client.force_login(self.manager)
        response = self.client.get(reverse('frontend:portal-inquiry-detail', args=[case.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Portal regression')

    def test_manager_pack_is_immutable_permission_scoped_and_downloadable(self):
        with tempfile.TemporaryDirectory() as media_root, override_settings(MEDIA_ROOT=media_root):
            pack, created = generate_management_pack(
                business_date=self.business_date, actor=self.manager, retention_days=7
            )
            self.assertTrue(created)
            self.assertTrue(pack.pdf_file.name.endswith('.pdf'))
            self.assertTrue(pack.csv_file.name.endswith('.csv'))
            duplicate, duplicate_created = generate_management_pack(
                business_date=self.business_date, actor=self.manager
            )
            self.assertFalse(duplicate_created)
            self.assertEqual(duplicate.pk, pack.pk)

            self.client.force_login(self.manager)
            pdf = self.client.get(reverse(
                'frontend:portal-management-pack-download', args=[pack.pk, 'pdf']
            ))
            self.assertEqual(pdf.status_code, 200)
            self.assertEqual(pdf['Content-Type'], 'application/pdf')
            pdf.close()
            self.client.force_login(self.guest)
            self.assertEqual(self.client.get(reverse(
                'frontend:portal-management-pack-download', args=[pack.pk, 'csv']
            )).status_code, 302)
