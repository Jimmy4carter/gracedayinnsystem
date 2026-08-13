import hashlib
import json
import csv
from io import BytesIO, StringIO
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q, Sum
from django.utils import timezone

from apps.billing.models import Folio, FolioEntry
from apps.housekeeping.models import HousekeepingTask, MaintenanceTicket
from apps.notifications.models import ChatConversation, InquiryCase, OutboundMessage
from apps.payments.models import CashierShift, Payment, PaymentRefund
from apps.reservations.models import Reservation
from apps.rooms.models import Room
from apps.services.models import ServiceOrder

from .models import DailyMetricSnapshot, ManagementPack, NightAuditRun


def money(value):
    return Decimal(str(value or 0)).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)


def calculate_financial_report(*, days=14):
    """Period-scoped finance view shared by HTML, CSV and PDF exports."""
    end = timezone.localdate()
    start = end - timedelta(days=max(days, 1) - 1)
    entries = FolioEntry.objects.filter(posted_at__date__range=(start, end))
    completed = Payment.objects.filter(status='completed', created_at__date__range=(start, end))
    refunds = PaymentRefund.objects.filter(created_at__date__range=(start, end))
    charges = entries.filter(direction='debit').exclude(entry_type__in=['payment', 'refund'])
    room = charges.filter(entry_type='accommodation').aggregate(total=Sum('amount'))['total'] or 0
    service = charges.filter(entry_type='service').aggregate(total=Sum('amount'))['total'] or 0
    tax = charges.filter(entry_type='tax').aggregate(total=Sum('amount'))['total'] or 0
    refund_total = refunds.aggregate(total=Sum('amount'))['total'] or 0
    tender = {
        key: money(completed.filter(method=key).aggregate(total=Sum('amount'))['total'])
        for key in ('cash', 'pos', 'bank_transfer', 'online')
    }
    open_receivables = sum((max(f.balance, Decimal('0')) for f in Folio.objects.filter(status='open')), Decimal('0'))
    shifts = CashierShift.objects.filter(opened_at__date__range=(start, end))
    variance = shifts.filter(status__in=['closed', 'approved']).aggregate(total=Sum('variance'))['total'] or 0
    return {
        'period_start': start, 'period_end': end, 'days': days,
        'total_revenue': money(room + service + tax - refund_total),
        'gross_revenue': money(room + service + tax), 'room_revenue': money(room),
        'service_revenue': money(service), 'tax_revenue': money(tax),
        'refunds': money(refund_total), 'payments_collected': money(sum(tender.values())),
        'open_balance': money(open_receivables), 'cash_variance': money(variance),
        'open_shifts': shifts.filter(status='open').count(),
        'payment_count': completed.count(), 'refund_count': refunds.count(),
        'tender': tender,
    }


def calculate_daily_metrics(business_date):
    available_rooms = Room.objects.filter(is_active=True).exclude(status__in=['out_of_order', 'maintenance']).count()
    occupied = Reservation.objects.filter(
        check_in_date__lte=business_date, check_out_date__gt=business_date,
        status__in=['checked_in', 'checked_out'],
    )
    occupied_rooms = occupied.values('room_id').distinct().count()
    entries = FolioEntry.objects.filter(posted_at__date=business_date)
    room_revenue = entries.filter(direction='debit', entry_type='accommodation').aggregate(total=Sum('amount'))['total'] or 0
    service_revenue = entries.filter(direction='debit', entry_type='service').aggregate(total=Sum('amount'))['total'] or 0
    refunds = entries.filter(direction='debit', entry_type='refund').aggregate(total=Sum('amount'))['total'] or 0
    total_revenue = money(room_revenue + service_revenue - refunds)
    receivables = sum((max(folio.balance, Decimal('0')) for folio in Folio.objects.filter(status='open')), Decimal('0'))
    variance = CashierShift.objects.filter(closed_at__date=business_date).aggregate(total=Sum('variance'))['total'] or 0
    sources = dict(
        Reservation.objects.filter(created_at__date=business_date).values_list('source').annotate(total=Count('id'))
    )
    hk_duration = HousekeepingTask.objects.filter(completed_at__date=business_date).aggregate(
        value=Avg(ExpressionWrapper(F('completed_at') - F('started_at'), output_field=DurationField()))
    )['value']
    service_duration = ServiceOrder.objects.filter(status='completed', updated_at__date=business_date).aggregate(
        value=Avg(ExpressionWrapper(F('updated_at') - F('created_at'), output_field=DurationField()))
    )['value']
    occupancy = money(Decimal(occupied_rooms) * 100 / available_rooms) if available_rooms else Decimal('0.00')
    adr = money(room_revenue / occupied_rooms) if occupied_rooms else Decimal('0.00')
    revpar = money(room_revenue / available_rooms) if available_rooms else Decimal('0.00')
    result = {
        'business_date': business_date, 'currency': settings.HOTEL_CURRENCY,
        'available_rooms': available_rooms, 'occupied_rooms': occupied_rooms,
        'occupancy_percent': occupancy, 'room_revenue': money(room_revenue),
        'service_revenue': money(service_revenue), 'total_revenue': total_revenue,
        'adr': adr, 'revpar': revpar, 'receivables': money(receivables),
        'cash_variance': money(variance), 'reservation_sources': sources,
        'operational_sla': {
            'housekeeping_minutes': round(hk_duration.total_seconds() / 60, 2) if hk_duration else None,
            'service_minutes': round(service_duration.total_seconds() / 60, 2) if service_duration else None,
        },
    }
    hash_data = {key: str(value) for key, value in result.items()}
    result['source_hash'] = hashlib.sha256(json.dumps(hash_data, sort_keys=True).encode()).hexdigest()
    return result


def calculate_booking_pace(*, as_of=None, window_days=7, arrival_horizon_days=30):
    as_of = as_of or timezone.now()
    today = timezone.localdate(as_of)
    arrival_end = today + timedelta(days=arrival_horizon_days)
    current_start = as_of - timedelta(days=window_days)
    prior_start = current_start - timedelta(days=window_days)
    base = Reservation.objects.filter(
        check_in_date__gte=today, check_in_date__lte=arrival_end,
        status__in=['pending', 'confirmed', 'checked_in'],
    )
    current = base.filter(created_at__gte=current_start, created_at__lte=as_of).count()
    prior = base.filter(created_at__gte=prior_start, created_at__lt=current_start).count()
    change = current - prior
    percent = money(Decimal(change) * 100 / prior) if prior else (Decimal('100.00') if current else Decimal('0.00'))
    return {
        'window_days': window_days, 'arrival_horizon_days': arrival_horizon_days,
        'current_bookings': current, 'prior_bookings': prior,
        'change': change, 'change_percent': percent,
    }


def calculate_management_exceptions(*, now=None):
    now = now or timezone.now()
    housekeeping_overdue = HousekeepingTask.objects.filter(
        status__in=['pending', 'in_progress'], scheduled_at__lt=now,
    ).count()
    room_discrepancies = Room.objects.filter(status='housekeeping').exclude(
        housekeeping_tasks__status__in=['pending', 'in_progress', 'completed']
    ).distinct().count()
    return {
        'housekeeping_overdue': housekeeping_overdue,
        'room_discrepancies': room_discrepancies,
        'maintenance_awaiting_approval': MaintenanceTicket.objects.filter(status='resolved').count(),
        'cash_variances_awaiting_approval': CashierShift.objects.filter(status='closed').exclude(variance=0).count(),
        'communication_failures': OutboundMessage.objects.filter(
            status__in=['failed', 'bounced', 'complained']
        ).count(),
        'communication_deferred': OutboundMessage.objects.filter(status='deferred').count(),
        'inquiries_overdue': InquiryCase.objects.filter(
            Q(first_response_due_at__lt=now, first_responded_at__isnull=True)
            | Q(resolution_due_at__lt=now, resolved_at__isnull=True)
        ).exclude(status__in=['resolved', 'closed', 'spam']).count(),
        'chat_queue_over_five_minutes': ChatConversation.objects.filter(
            status='queued', created_at__lt=now - timedelta(minutes=5)
        ).count(),
    }


def _json_safe(value):
    if isinstance(value, Decimal):
        return str(value)
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    if isinstance(value, dict):
        return {key: _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value


@transaction.atomic
def generate_management_pack(*, business_date, actor=None, retention_days=30):
    existing = ManagementPack.objects.filter(business_date=business_date).first()
    if existing:
        return existing, False
    metrics = _json_safe(calculate_daily_metrics(business_date))
    pace = _json_safe(calculate_booking_pace())
    exceptions = _json_safe(calculate_management_exceptions())

    csv_buffer = StringIO()
    writer = csv.writer(csv_buffer)
    writer.writerow(['GraceDay Inn manager pack', business_date.isoformat()])
    writer.writerow(['Metric', 'Value'])
    for key, value in metrics.items():
        writer.writerow([key, json.dumps(value, sort_keys=True) if isinstance(value, (dict, list)) else value])
    writer.writerow([])
    writer.writerow(['Booking pace', json.dumps(pace, sort_keys=True)])
    writer.writerow(['Exceptions', json.dumps(exceptions, sort_keys=True)])

    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError as exc:
        raise ValidationError('reportlab is required to generate manager packs.') from exc
    pdf_buffer = BytesIO()
    pdf = canvas.Canvas(pdf_buffer, pagesize=A4)
    _, height = A4
    y = height - 48
    pdf.setFont('Helvetica-Bold', 15)
    pdf.drawString(40, y, f'GraceDay Inn Manager Pack — {business_date}')
    y -= 28
    pdf.setFont('Helvetica', 9)
    rows = [
        ('Occupancy', f"{metrics['occupancy_percent']}%"),
        ('Room revenue', f"{metrics['currency']} {metrics['room_revenue']}"),
        ('Total revenue', f"{metrics['currency']} {metrics['total_revenue']}"),
        ('ADR', f"{metrics['currency']} {metrics['adr']}"),
        ('RevPAR', f"{metrics['currency']} {metrics['revpar']}"),
        ('Receivables', f"{metrics['currency']} {metrics['receivables']}"),
        ('Booking pace', f"{pace['current_bookings']} vs {pace['prior_bookings']} prior"),
    ] + [(f'Exception — {key.replace("_", " ")}', value) for key, value in exceptions.items()]
    for label, value in rows:
        if y < 45:
            pdf.showPage(); y = height - 48; pdf.setFont('Helvetica', 9)
        pdf.drawString(40, y, f'{label}: {value}')
        y -= 16
    pdf.save()

    pack = ManagementPack(
        business_date=business_date, metrics=metrics, booking_pace=pace,
        exceptions=exceptions, generated_by=actor,
        expires_at=timezone.now() + timedelta(days=retention_days),
    )
    pack.pdf_file.save(f'graceday-manager-pack-{business_date}.pdf', ContentFile(pdf_buffer.getvalue()), save=False)
    pack.csv_file.save(f'graceday-manager-pack-{business_date}.csv', ContentFile(csv_buffer.getvalue().encode()), save=False)
    pack.save()
    return pack, True


@transaction.atomic
def run_night_audit(*, business_date, actor):
    if NightAuditRun.objects.filter(business_date=business_date).exists():
        raise ValidationError('Night audit has already completed for this business date.')
    if business_date >= timezone.localdate():
        raise ValidationError('Night audit can only close a completed business date.')
    open_shifts = CashierShift.objects.filter(status='open', opened_at__date__lte=business_date).count()
    unresolved_departures = Reservation.objects.filter(
        check_out_date__lte=business_date, status='checked_in'
    ).count()
    unresolved_arrivals = Reservation.objects.filter(
        check_in_date__lte=business_date, status__in=['pending', 'confirmed']
    ).count()
    exceptions = {
        'open_cashier_shifts': open_shifts, 'unresolved_departures': unresolved_departures,
        'unresolved_arrivals': unresolved_arrivals,
    }
    if any(exceptions.values()):
        raise ValidationError(f'Night audit blocked by operational exceptions: {exceptions}')
    snapshot = DailyMetricSnapshot.objects.create(
        generated_by=actor, **calculate_daily_metrics(business_date)
    )
    return NightAuditRun.objects.create(
        business_date=business_date, snapshot=snapshot,
        exception_summary=exceptions, completed_by=actor,
    )
