import csv
import json
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.tokens import default_token_generator
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Prefetch, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from django.utils.dateparse import parse_date

from apps.accounts.models import DataPrivacyRequest, GuestProfile, StaffMFADevice, UserProfile
from apps.accounts.mfa import (
    begin_mfa_enrollment, confirm_mfa_enrollment, staff_mfa_required, verify_mfa_code,
)
from apps.accounts.privacy import (
    execute_privacy_request, review_privacy_request, submit_privacy_request,
)
from apps.accounts.security import (
    clear_account_login_failures,
    login_is_blocked,
    record_authentication_event,
    record_login_failure,
)
from apps.billing.models import FinancialAuditRun, Folio, Invoice, InvoiceItem, Receipt
from apps.billing.financial_audit import approve_financial_audit, prepare_financial_audit
from apps.billing.services import post_financial_correction, tax_summary
from apps.housekeeping.models import (
    HousekeepingTask, IncidentReport, LostFoundItem, MaintenanceTicket,
    StockBalance, StockMovement,
)
from apps.housekeeping.services import (
    create_housekeeping_task, create_incident, create_maintenance_ticket,
    record_stock_movement, register_lost_found_item, transfer_stock,
    transition_housekeeping_task, transition_incident,
    transition_lost_found_item, transition_maintenance_ticket,
)
from apps.notifications.models import (
    BrevoContactSync, ChatCannedReply, ChatConversation, ContactPreference, InquiryCase, JobExecution, Notification,
    OperationalAlert, ScheduledJob, Suppression,
)
from apps.notifications.chat import (
    can_access_conversation, send_chat_message, start_conversation,
    submit_chat_satisfaction, transition_chat,
)
from apps.notifications.inquiries import (
    add_inquiry_attachment, add_inquiry_reply, create_inquiry, transition_inquiry,
)
from apps.notifications.services import enqueue_email
from apps.notifications.alerts import transition_alert
from apps.payments.models import CashierShift, CashierTerminal, Payment
from apps.payments.services import (
    close_cashier_shift, get_open_shift, open_cashier_shift, record_payment,
    request_receipt_print,
)
from apps.reservations.models import (
    BookingQuote, CorporateAccount, GroupBooking, GuestCompanion, GuestConsentHistory,
    Reservation, ReservationDiscountRequest,
)
from apps.reservations.services import (
    amend_reservation_stay, create_reservation, move_reservation_room,
    request_reservation_discount, review_reservation_discount, transition_reservation,
)
from apps.reservations.pricing import convert_quote, create_quote, release_quote
from apps.rooms.models import Amenity, InventoryBlock, Promotion, Room, RoomImage, RoomType, RoomTypeImage
from apps.rooms.inventory import create_inventory_block, release_inventory_block
from apps.services.models import MenuItem, ServiceCategory, ServiceOrder
from apps.services.services import transition_service_order

from .decorators import action_role_required, role_required
from .forms import (
    AmenityCreateForm,
    BookingRequestForm,
    RoomSearchForm,
    ContactForm,
    GuestCreateForm,
    HousekeepingTaskCreateForm,
    IncidentReportCreateForm,
    LostFoundItemCreateForm,
    MaintenanceTicketCreateForm,
    NewsletterMessageForm,
    PaymentRecordForm,
    ServiceOrderCreateForm,
    PortalReservationForm,
    PortalLoginForm,
    PortalSignUpForm,
    RoomCreateForm,
    RoomTypeCreateForm,
    StockMovementForm,
)
from .models import (
    AuditLog, DailyMetricSnapshot, FAQItem, FeatureFlag, GuestTestimonial, LocalGuidePlace, ManagementPack,
    ManagementQuery, NewsletterSubscription, NewsletterMessage, NightAuditRun, OperationalSetting,
    PolicyDocument,
)
from .management_queries import (
    add_management_query_note, create_management_query, transition_management_query,
)
from .reporting import (
    calculate_booking_pace, calculate_daily_metrics, calculate_management_exceptions,
    calculate_financial_report, generate_management_pack, run_night_audit,
)
from .security import begin_booking_verification, check_booking_verification, clear_booking_verification
from .analytics import record_event
from .feature_flags import flag_enabled

logger = logging.getLogger(__name__)

FRONTEND_ROUTE_PREFIX = 'frontend:'
PORTAL_DASHBOARD_ROUTE = f'{FRONTEND_ROUTE_PREFIX}portal-dashboard'
PORTAL_RESERVATIONS_ROUTE = f'{FRONTEND_ROUTE_PREFIX}portal-reservations'
PORTAL_PAYMENTS_ROUTE = f'{FRONTEND_ROUTE_PREFIX}portal-payments'
PORTAL_SERVICES_ROUTE = f'{FRONTEND_ROUTE_PREFIX}portal-services'
PORTAL_HOUSEKEEPING_ROUTE = f'{FRONTEND_ROUTE_PREFIX}portal-housekeeping'
STAFF_ROLES = {'admin', 'manager', 'receptionist', 'accountant'}
RESERVATIONS_LINK = '/portal/reservations/'
PAYMENTS_LINK = '/portal/payments/'
SERVICES_LINK = '/portal/services/'
HOUSEKEEPING_LINK = '/portal/housekeeping/'
PORTAL_BILLING_LINK = '/portal/billing/'
ALLOWED_REPORT_WINDOWS = {7, 14, 30, 90}

PUBLIC_INDEX_ROUTES = (
    'public-home', 'public-rooms', 'public-about', 'public-offers',
    'public-dining', 'public-laundry', 'public-guide', 'public-blog', 'public-contact',
    'public-faq', 'public-policies',
)


def robots_txt(request):
    sitemap_url = request.build_absolute_uri(reverse('frontend:public-sitemap'))
    return HttpResponse(
        f'User-agent: *\nAllow: /\nDisallow: /portal/\nSitemap: {sitemap_url}\n',
        content_type='text/plain',
    )


def public_sitemap(request):
    urls = [request.build_absolute_uri(reverse(f'frontend:{route}')) for route in PUBLIC_INDEX_ROUTES]
    urls.extend(
        request.build_absolute_uri(reverse('frontend:public-room-detail', args=[room_id]))
        for room_id in Room.objects.filter(is_active=True).values_list('id', flat=True)
    )
    urls.extend(
        request.build_absolute_uri(reverse('frontend:public-policy-detail', args=[slug]))
        for slug in PolicyDocument.objects.filter(is_published=True).values_list('slug', flat=True)
    )
    body = ''.join(f'<url><loc>{url}</loc></url>' for url in urls)
    return HttpResponse(
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f'{body}</urlset>',
        content_type='application/xml',
    )


def _duration_to_minutes(duration):
    if not duration:
        return 0
    return round(duration.total_seconds() / 60, 2)


def _selected_window_days(request, default=14):
    raw_days = request.GET.get('days')
    try:
        days = int(raw_days) if raw_days else default
    except (TypeError, ValueError):
        days = default
    return days if days in ALLOWED_REPORT_WINDOWS else default


def _build_trend_series(days=14, user=None):
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    labels = [start + timedelta(days=index) for index in range(days)]

    active_reservation_statuses = {'confirmed', 'checked_in', 'checked_out'}
    total_rooms = max(Room.objects.filter(is_active=True).count(), 1)
    reservation_scope = Reservation.objects.filter(status__in=active_reservation_statuses)
    payment_scope = Payment.objects.filter(status='completed')
    service_scope = ServiceOrder.objects.filter(status='completed')
    if user and user.role == 'guest':
        reservation_scope = reservation_scope.filter(guest=user)
        payment_scope = payment_scope.filter(invoice__guest=user)
        service_scope = service_scope.filter(guest=user)
    elif user and user.role == 'housekeeping':
        reservation_scope = reservation_scope.none()
        payment_scope = payment_scope.none()
        service_scope = service_scope.none()

    occupancy_trend = []
    for day in labels:
        occupied_count = reservation_scope.filter(
            check_in_date__lte=day,
            check_out_date__gt=day,
        ).count()
        occupancy_trend.append(round((occupied_count / total_rooms) * 100, 2))

    revenue_map = {
        row['day']: float(row['total'] or 0)
        for row in payment_scope.filter(
            created_at__date__range=(start, today),
        )
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(total=Sum('amount'))
    }
    revenue_trend = [round(revenue_map.get(day, 0.0), 2) for day in labels]

    service_sla_map = {
        row['day']: _duration_to_minutes(row['avg_duration'])
        for row in service_scope.filter(
            updated_at__date__range=(start, today),
        )
        .annotate(day=TruncDate('updated_at'))
        .values('day')
        .annotate(
            avg_duration=Avg(
                ExpressionWrapper(
                    F('updated_at') - F('created_at'),
                    output_field=DurationField(),
                )
            )
        )
    }
    service_sla_trend = [service_sla_map.get(day, 0) for day in labels]

    return {
        'labels': [day.strftime('%Y-%m-%d') for day in labels],
        'occupancy_trend': occupancy_trend,
        'revenue_trend': revenue_trend,
        'service_sla_trend': service_sla_trend,
    }


def _build_report_data(days=14):
    reservations = Reservation.objects.all()
    service_sla_duration = ServiceOrder.objects.filter(status='completed').aggregate(
        avg_duration=Avg(
            ExpressionWrapper(
                F('updated_at') - F('created_at'),
                output_field=DurationField(),
            )
        )
    )['avg_duration']
    housekeeping_turnaround_duration = HousekeepingTask.objects.filter(
        status__in=['completed', 'verified'],
        completed_at__isnull=False,
    ).aggregate(
        avg_duration=Avg(
            ExpressionWrapper(
                F('completed_at') - Coalesce(F('started_at'), F('created_at')),
                output_field=DurationField(),
            )
        )
    )['avg_duration']

    report = {
        **calculate_financial_report(days=days),
        'occupied_rooms': Room.objects.filter(status='occupied').count(),
        'available_rooms': Room.objects.filter(status='available').count(),
        'pending_housekeeping': HousekeepingTask.objects.filter(status='pending').count(),
        'total_reservations': reservations.count(),
        'confirmed_reservations': reservations.filter(status='confirmed').count(),
        'service_sla_minutes': _duration_to_minutes(service_sla_duration),
        'housekeeping_turnaround_minutes': _duration_to_minutes(housekeeping_turnaround_duration),
        'completed_service_orders': ServiceOrder.objects.filter(status='completed').count(),
        'completed_housekeeping_tasks': HousekeepingTask.objects.filter(status__in=['completed', 'verified']).count(),
    }
    return report, _build_trend_series(days=days)


def _render_report_pdf(report, trend, days=14):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError:
        response = HttpResponse('PDF export dependency is missing. Install reportlab.', status=501)
        response['Content-Type'] = 'text/plain; charset=utf-8'
        return response

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="graceday-inn-report-{days}d.pdf"'
    pdf = canvas.Canvas(response, pagesize=A4)
    _, height = A4
    y = height - 48

    pdf.setFont('Helvetica-Bold', 14)
    pdf.drawString(40, y, 'GRACEDAY INN - Performance Report')
    y -= 24

    pdf.setFont('Helvetica', 10)
    pdf.drawString(40, y, f'Generated: {timezone.localtime().strftime("%Y-%m-%d %H:%M") }')
    y -= 28

    for label, value in [
        ('Total Revenue', report['total_revenue']),
        ('Open Balance', report['open_balance']),
        ('Total Reservations', report['total_reservations']),
        ('Confirmed Reservations', report['confirmed_reservations']),
        ('Occupied Rooms', report['occupied_rooms']),
        ('Available Rooms', report['available_rooms']),
        ('Pending Housekeeping', report['pending_housekeeping']),
        ('Service SLA (Avg Min)', report['service_sla_minutes']),
        ('Housekeeping Turnaround (Avg Min)', report['housekeeping_turnaround_minutes']),
        ('Completed Service Orders', report['completed_service_orders']),
        ('Completed Housekeeping Tasks', report['completed_housekeeping_tasks']),
    ]:
        if y < 56:
            pdf.showPage()
            y = height - 48
            pdf.setFont('Helvetica', 10)
        pdf.drawString(40, y, f'{label}: {value}')
        y -= 16

    if y < 120:
        pdf.showPage()
        y = height - 48
    y -= 10
    pdf.setFont('Helvetica-Bold', 11)
    pdf.drawString(40, y, '14-Day Trend Snapshot')
    y -= 18
    pdf.setFont('Helvetica', 9)
    rows = zip(
        trend['labels'],
        trend['occupancy_trend'],
        trend['revenue_trend'],
        trend['service_sla_trend'],
    )
    for day, occupancy, revenue, sla in rows:
        if y < 40:
            pdf.showPage()
            y = height - 40
            pdf.setFont('Helvetica', 9)
        pdf.drawString(
            40,
            y,
            f'{day}  |  Occupancy: {occupancy}%  |  Revenue: N{revenue}  |  Service SLA: {sla} min',
        )
        y -= 14

    pdf.showPage()
    pdf.save()
    return response


def _build_report_data(days=14):
    reservations = Reservation.objects.all()
    service_sla_duration = ServiceOrder.objects.filter(status='completed').aggregate(
        avg_duration=Avg(
            ExpressionWrapper(
                F('updated_at') - F('created_at'),
                output_field=DurationField(),
            )
        )
    )['avg_duration']
    housekeeping_turnaround_duration = HousekeepingTask.objects.filter(
        status__in=['completed', 'verified'],
        completed_at__isnull=False,
    ).aggregate(
        avg_duration=Avg(
            ExpressionWrapper(
                F('completed_at') - Coalesce(F('started_at'), F('created_at')),
                output_field=DurationField(),
            )
        )
    )['avg_duration']

    report = {
        **calculate_financial_report(days=days),
        'occupied_rooms': Room.objects.filter(status='occupied').count(),
        'available_rooms': Room.objects.filter(status='available').count(),
        'pending_housekeeping': HousekeepingTask.objects.filter(status='pending').count(),
        'total_reservations': reservations.count(),
        'confirmed_reservations': reservations.filter(status='confirmed').count(),
        'service_sla_minutes': _duration_to_minutes(service_sla_duration),
        'housekeeping_turnaround_minutes': _duration_to_minutes(housekeeping_turnaround_duration),
        'completed_service_orders': ServiceOrder.objects.filter(status='completed').count(),
        'completed_housekeeping_tasks': HousekeepingTask.objects.filter(status__in=['completed', 'verified']).count(),
    }
    return report, _build_trend_series(days=days)


def _render_report_pdf(report, trend, days=14):
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas
    except ImportError:
        response = HttpResponse('PDF export dependency is missing. Install reportlab.', status=501)
        response['Content-Type'] = 'text/plain; charset=utf-8'
        return response

    response = HttpResponse(content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="graceday-inn-report-{days}d.pdf"'

    pdf = canvas.Canvas(response, pagesize=A4)
    _, height = A4
    y = height - 48

    pdf.setFont('Helvetica-Bold', 14)
    pdf.drawString(40, y, 'GRACEDAY INN - Performance Report')
    y -= 24

    pdf.setFont('Helvetica', 10)
    pdf.drawString(40, y, f'Generated: {timezone.localtime().strftime("%Y-%m-%d %H:%M") }')
    y -= 28

    for label, value in [
        ('Total Revenue', report['total_revenue']),
        ('Open Balance', report['open_balance']),
        ('Total Reservations', report['total_reservations']),
        ('Confirmed Reservations', report['confirmed_reservations']),
        ('Occupied Rooms', report['occupied_rooms']),
        ('Available Rooms', report['available_rooms']),
        ('Pending Housekeeping', report['pending_housekeeping']),
        ('Service SLA (Avg Min)', report['service_sla_minutes']),
        ('Housekeeping Turnaround (Avg Min)', report['housekeeping_turnaround_minutes']),
        ('Completed Service Orders', report['completed_service_orders']),
        ('Completed Housekeeping Tasks', report['completed_housekeeping_tasks']),
    ]:
        if y < 56:
            pdf.showPage()
            y = height - 48
            pdf.setFont('Helvetica', 10)
        pdf.drawString(40, y, f'{label}: {value}')
        y -= 16

    if y < 120:
        pdf.showPage()
        y = height - 48
    y -= 10
    pdf.setFont('Helvetica-Bold', 11)
    pdf.drawString(40, y, '14-Day Trend Snapshot')
    y -= 18
    pdf.setFont('Helvetica', 9)
    rows = zip(
        trend['labels'],
        trend['occupancy_trend'],
        trend['revenue_trend'],
        trend['service_sla_trend'],
    )
    for day, occupancy, revenue, sla in rows:
        if y < 40:
            pdf.showPage()
            y = height - 40
            pdf.setFont('Helvetica', 9)
        pdf.drawString(
            40,
            y,
            f'{day}  |  Occupancy: {occupancy}%  |  Revenue: N{revenue}  |  Service SLA: {sla} min',
        )
        y -= 14

    pdf.showPage()
    pdf.save()
    return response


def _log_audit(request, event_type, action, target_model, target_id='', details=None):
    AuditLog.objects.create(
        actor=request.user if request.user.is_authenticated else None,
        event_type=event_type,
        action=action,
        target_model=target_model,
        target_id=str(target_id or ''),
        details=details or {},
        ip_address=request.META.get('REMOTE_ADDR'),
        user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:255],
    )


def _notify_user(recipient, title, message, notification_type='general', link=''):
    Notification.objects.create(
        recipient=recipient,
        title=title,
        message=message,
        notification_type=notification_type,
        link=link,
    )


def _notify_staff(title, message, notification_type='system', link=''):
    staff_users = UserProfile.objects.filter(role__in=STAFF_ROLES, is_active=True)
    notifications = [
        Notification(
            recipient=staff,
            title=title,
            message=message,
            notification_type=notification_type,
            link=link,
        )
        for staff in staff_users
    ]
    if notifications:
        Notification.objects.bulk_create(notifications)


def _ensure_invoice_for_reservation(reservation):
    invoice, created = Invoice.objects.get_or_create(
        reservation=reservation,
        defaults={
            'guest': reservation.guest,
            'status': 'sent',
            'due_date': reservation.check_in_date,
            'notes': f'Generated for reservation {reservation.reservation_number}.',
        },
    )
    if created:
        InvoiceItem.objects.create(
            invoice=invoice,
            description=f'Accommodation charge ({reservation.reservation_number})',
            quantity=max(reservation.nights, 1),
            unit_price=reservation.nightly_rate,
        )
        invoice.save()
    return invoice





def _portal_stats(user):
    cache_key = f'portal_stats_{user.id}_{user.role}'
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    room_counts = Room.objects.values('status').annotate(total=Count('id'))
    room_status = {item['status']: item['total'] for item in room_counts}
    today = timezone.localdate()
    reservations_qs = Reservation.objects.select_related('guest', 'room', 'room__room_type')
    if user.role == 'guest':
        reservations_qs = reservations_qs.filter(guest=user)
    elif user.role == 'housekeeping':
        reservations_qs = reservations_qs.none()
    invoices_qs = Invoice.objects.select_related('guest', 'reservation')
    if user.role == 'guest':
        invoices_qs = invoices_qs.filter(guest=user)
    elif user.role not in STAFF_ROLES:
        invoices_qs = invoices_qs.none()

    service_orders_qs = ServiceOrder.objects.all()
    if user.role == 'guest':
        service_orders_qs = service_orders_qs.filter(guest=user)
    elif user.role == 'housekeeping':
        service_orders_qs = service_orders_qs.none()
    service_sla_duration = service_orders_qs.filter(status='completed').aggregate(
        avg_duration=Avg(
            ExpressionWrapper(
                F('updated_at') - F('created_at'),
                output_field=DurationField(),
            )
        )
    )['avg_duration']

    housekeeping_qs = HousekeepingTask.objects.all()
    if user.role == 'housekeeping':
        housekeeping_qs = housekeeping_qs.filter(assigned_to=user)
    elif user.role == 'guest':
        housekeeping_qs = housekeeping_qs.none()
    housekeeping_turnaround_duration = housekeeping_qs.filter(
        status__in=['completed', 'verified'],
        completed_at__isnull=False,
    ).aggregate(
        avg_duration=Avg(
            ExpressionWrapper(
                F('completed_at') - Coalesce(F('started_at'), F('created_at')),
                output_field=DurationField(),
            )
        )
    )['avg_duration']

    result = {
        'reservation_count': reservations_qs.count(),
        'checkin_today': reservations_qs.filter(check_in_date=today).count(),
        'checkout_today': reservations_qs.filter(check_out_date=today).count(),
        'pending_reservations': reservations_qs.filter(status='pending').count(),
        'available_rooms': room_status.get('available', 0),
        'occupied_rooms': room_status.get('occupied', 0),
        'housekeeping_rooms': room_status.get('housekeeping', 0),
        'invoice_balance': invoices_qs.aggregate(total=Sum('balance'))['total'] or 0,
        'unread_notifications': Notification.objects.filter(recipient=user, is_read=False).count(),
        'service_sla_minutes': _duration_to_minutes(service_sla_duration),
        'housekeeping_turnaround_minutes': _duration_to_minutes(housekeeping_turnaround_duration),
    }
    cache.set(cache_key, result, 90)
    return result


def home(request):
    featured_gallery = RoomTypeImage.objects.filter(is_published=True).order_by(
        '-is_featured', 'display_order', 'id'
    )
    featured_rooms = RoomType.objects.prefetch_related(
        'amenities',
        Prefetch('gallery_images', queryset=featured_gallery, to_attr='public_gallery'),
    ).order_by('name', 'id')[:6]
    featured_menu_items = MenuItem.objects.filter(is_available=True).select_related('category')[:6]
    amenity_names = [
        'WiFi',
        'Air Conditioning',
        'TV',
        'Laundry',
        'Conference Room',
        'Bathtub',
        'Scenic Views',
        'Balcony',
        'Coffee Maker',
        'Iron & Board',
        'Room Service',
    ]
    initial = {
        'check_in_date': request.GET.get('check_in_date') or (timezone.localdate() + timedelta(days=1)).isoformat(),
        'check_out_date': request.GET.get('check_out_date') or (timezone.localdate() + timedelta(days=2)).isoformat(),
        'num_adults': request.GET.get('num_adults') or 1,
        'num_children': request.GET.get('num_children') or 0,
        'room_type': request.GET.get('room_type'),
    }
    search_form = RoomSearchForm(initial=initial)
    record_event(request, 'home_page_view', source='homepage')
    context = {
        'search_form': search_form,
        'featured_rooms': featured_rooms,
        'featured_menu_items': featured_menu_items,
        'amenity_names': amenity_names,
        'hotel_metrics': {
            'active_rooms': Room.objects.filter(is_active=True).count(),
            'available_rooms': Room.objects.filter(is_active=True, status='available').count(),
            'room_types': RoomType.objects.count(),
            'service_categories': ServiceCategory.objects.count(),
        },
        'today': timezone.localdate(),
    }
    return render(request, 'publicsite/index.html', context)


def public_quote_confirm(request):
    booking_data = request.session.get('pending_quote_booking') or {}
    quote = BookingQuote.objects.select_related('room', 'room__room_type', 'rate_plan', 'promotion').filter(
        pk=booking_data.get('quote_id')
    ).first()
    if not quote or quote.status != 'active' or quote.expires_at <= timezone.now():
        if quote and quote.status == 'active':
            release_quote(quote_id=quote.id)
        request.session.pop('pending_quote_booking', None)
        messages.error(request, 'Your quote has expired. Please choose your stay again.')
        record_event(request, 'booking_error', error_code='quote_expired')
        return redirect('frontend:public-home')

    if request.method == 'POST' and request.POST.get('action') == 'cancel':
        release_quote(quote_id=quote.id)
        request.session.pop('pending_quote_booking', None)
        record_event(request, 'quote_cancelled', quote_reference=str(quote.reference))
        return redirect('frontend:public-home')

    if request.method == 'POST':
        if request.user.is_authenticated:
            try:
                reservation = convert_quote(
                    quote_id=quote.id, guest=request.user, created_by=request.user,
                    source='direct_website',
                    notes=f"Requested via website. Contact: {booking_data.get('phone') or 'N/A'}",
                )
            except ValidationError as exc:
                messages.error(request, '; '.join(exc.messages))
                return redirect('frontend:public-home')
            request.session.pop('pending_quote_booking', None)
            _notify_staff(
                title='New booking request',
                message=f'Booking {reservation.reservation_number} created for Room {reservation.room.number}.',
                notification_type='reservation', link=RESERVATIONS_LINK,
            )
            record_event(
                request, 'booking_conversion', reservation_number=reservation.reservation_number,
                quote_reference=str(quote.reference), source='direct_website',
            )
            messages.success(request, f'Booking request {reservation.reservation_number} created successfully.')
            return redirect('frontend:portal-my-stay' if request.user.role == 'guest' else 'frontend:portal-dashboard')

        code = begin_booking_verification(request, booking_data)
        if code is None:
            release_quote(quote_id=quote.id)
            messages.error(request, 'Too many verification requests. Please wait before trying again.')
            return redirect('frontend:public-home')
        sent = send_html_email(
            subject='GRACEDAY INN - Verify your booking', template_name='emails/verify_email.html',
            context={'first_name': booking_data['first_name'], 'code': code},
            recipient_list=[booking_data['email']],
        )
        if not sent:
            release_quote(quote_id=quote.id)
            clear_booking_verification(request)
            messages.error(request, 'We could not send the verification email. Please try again shortly.')
            return redirect('frontend:public-home')
        request.session.pop('pending_quote_booking', None)
        record_event(request, 'quote_confirmed', quote_reference=str(quote.reference))
        messages.info(request, 'A verification code has been sent to your email. It expires in 10 minutes.')
        return redirect('frontend:portal-verify-booking')

    record_event(request, 'quote_view', quote_reference=str(quote.reference))
    return render(request, 'publicsite/quote-confirm.html', {'quote': quote, 'booking_data': booking_data})


def about(request):
    return render(
        request,
        'publicsite/about-us.html',
        {
            'about_stats': {
                'rooms': Room.objects.filter(is_active=True).count(),
                'room_types': RoomType.objects.count(),
                'amenities': Amenity.objects.count(),
                'menu_items': MenuItem.objects.filter(is_available=True).count(),
            },
            'top_amenities': Amenity.objects.all()[:6],
        },
    )


def public_guide(request):
    language = (request.GET.get('lang') or request.session.get('public_language') or 'en').lower()
    if language not in {'en', 'fr', 'ha'}:
        language = 'en'
    places = list(LocalGuidePlace.objects.filter(is_published=True).prefetch_related('translations'))
    for place in places:
        translation = next(
            (item for item in place.translations.all()
             if item.language_code == language and item.is_published),
            None,
        )
        place.localized_name = translation.name if translation else place.name
        place.localized_summary = translation.summary if translation else place.summary
        place.localized_address = translation.address if translation else place.address

    if request.method == 'POST':
        try:
            testimonial = GuestTestimonial(
                guest=request.user if request.user.is_authenticated and request.user.role == 'guest' else None,
                display_name=(request.POST.get('display_name') or '').strip(),
                rating=int(request.POST.get('rating', 0)),
                body=(request.POST.get('body') or '').strip(),
                publication_consent=request.POST.get('publication_consent') == 'on',
            )
            testimonial.full_clean()
            testimonial.save()
        except (ValidationError, ValueError, TypeError) as exc:
            messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
        else:
            messages.success(request, 'Thank you. Your review was submitted for moderation.')
            return redirect('frontend:public-guide')
    return render(request, 'publicsite/local-guide.html', {
        'guide_places': places,
        'testimonials': GuestTestimonial.objects.filter(
            status='approved', publication_consent=True,
        )[:12],
    })


def public_search(request):
    query = (request.GET.get('q') or '').strip()
    if not query:
        return redirect('frontend:public-home')

    query_lower = query.lower()
    navigation = {
        'home': 'frontend:public-home',
        'rooms': 'frontend:public-rooms',
        'about': 'frontend:public-about',
        'blog': 'frontend:public-blog',
        'news': 'frontend:public-blog',
        'contact': 'frontend:public-contact',
        'offers': 'frontend:public-offers',
        'dining': 'frontend:public-dining',
        'restaurant': 'frontend:public-dining',
        'laundry': 'frontend:public-laundry',
        'guide': 'frontend:public-guide',
        'abuja': 'frontend:public-guide',
        'faq': 'frontend:public-faq',
        'help': 'frontend:public-faq',
        'policies': 'frontend:public-policies',
        'privacy': 'frontend:public-policies',
        'cancellation': 'frontend:public-policies',
    }

    navigation_results = []
    for label, route in navigation.items():
        if label in query_lower or query_lower in label:
            navigation_results.append({'title': label.title(), 'url': reverse(route)})

    room_results = Room.objects.filter(is_active=True).filter(
        Q(number__icontains=query)
        | Q(description__icontains=query)
        | Q(room_type__name__icontains=query)
        | Q(room_type__description__icontains=query)
        | Q(room_type__amenities__name__icontains=query)
    ).distinct()

    room_type_results = RoomType.objects.filter(
        Q(name__icontains=query)
        | Q(description__icontains=query)
        | Q(amenities__name__icontains=query)
    ).distinct()

    service_results = MenuItem.objects.filter(is_available=True).filter(
        Q(name__icontains=query)
        | Q(description__icontains=query)
        | Q(category__name__icontains=query)
    ).distinct()

    category_results = ServiceCategory.objects.filter(
        Q(name__icontains=query)
        | Q(description__icontains=query)
    ).distinct()

    faq_results = FAQItem.objects.filter(is_published=True).filter(
        Q(question__icontains=query) | Q(answer__icontains=query)
    )
    policy_results = PolicyDocument.objects.filter(is_published=True).filter(
        Q(title__icontains=query) | Q(summary__icontains=query) | Q(body__icontains=query)
    )

    result_count = (
        len(navigation_results) + room_results.count() + room_type_results.count()
        + service_results.count() + category_results.count() + faq_results.count()
        + policy_results.count()
    )
    record_event(request, 'site_search', query_length=len(query), result_count=result_count)

    return render(
        request,
        'publicsite/search-results.html',
        {
            'query': query,
            'navigation_results': navigation_results,
            'room_results': room_results,
            'room_type_results': room_type_results,
            'service_results': service_results,
            'category_results': category_results,
            'faq_results': faq_results,
            'policy_results': policy_results,
        },
    )


def public_rooms(request):
    public_images = RoomTypeImage.objects.filter(is_published=True).order_by(
        '-is_featured', 'display_order', 'id'
    )
    rooms_qs = Room.objects.select_related('room_type').prefetch_related('gallery_images',
        Prefetch('room_type__gallery_images', queryset=public_images, to_attr='public_gallery')
    ).filter(is_active=True, is_sellable=True)

    from apps.reservations.pricing import expire_stale_holds
    expire_stale_holds()

    room_type_id = request.GET.get('room_type')
    room_type_slug = request.GET.get('category')
    check_in_str = request.GET.get('check_in_date')
    check_out_str = request.GET.get('check_out_date')
    num_adults = request.GET.get('num_adults')
    num_children = request.GET.get('num_children')

    if check_in_str and check_out_str:
        try:
            from django.utils.dateparse import parse_date
            check_in = parse_date(check_in_str)
            check_out = parse_date(check_out_str)
            if check_in and check_out and check_in < check_out:
                from django.utils import timezone
                from apps.reservations.models import Reservation, InventoryHold
                from apps.rooms.models import InventoryBlock
                
                conflicting_reservations = Reservation.objects.filter(
                    status__in=['pending', 'confirmed', 'checked_in'],
                    check_in_date__lt=check_out,
                    check_out_date__gt=check_in,
                ).values_list('room_id', flat=True)
                rooms_qs = rooms_qs.exclude(id__in=conflicting_reservations)

                conflicting_holds = InventoryHold.objects.filter(
                    status='active',
                    expires_at__gt=timezone.now(),
                    quote__check_in_date__lt=check_out,
                    quote__check_out_date__gt=check_in,
                ).values_list('room_id', flat=True)
                rooms_qs = rooms_qs.exclude(id__in=conflicting_holds)

                conflicting_blocks = InventoryBlock.objects.filter(
                    status='active',
                    start_date__lt=check_out,
                    end_date__gt=check_in,
                ).values_list('room_id', flat=True)
                rooms_qs = rooms_qs.exclude(id__in=conflicting_blocks)
        except Exception:
            pass

    total_guests = 0
    try:
        if num_adults:
            total_guests += int(num_adults)
        if num_children:
            total_guests += int(num_children)
    except (TypeError, ValueError):
        pass

    if total_guests > 0:
        rooms_qs = rooms_qs.filter(room_type__max_occupancy__gte=total_guests)

    if room_type_id:
        rooms_qs = rooms_qs.filter(room_type_id=room_type_id)
    if room_type_slug:
        rooms_qs = rooms_qs.filter(room_type__slug=room_type_slug)

    max_price = request.GET.get('max_price')
    if max_price:
        try:
            rooms_qs = rooms_qs.filter(room_type__base_price__lte=max_price)
        except (TypeError, ValueError):
            pass

    paginator = Paginator(rooms_qs, 9)
    page_number = request.GET.get('page')
    rooms = paginator.get_page(page_number)

    params = request.GET.copy()
    params.pop('page', None)
    querystring = params.urlencode()

    context = {
        'rooms': rooms,
        'page_obj': rooms,
        'paginator': paginator,
        'querystring': querystring,
        'room_types': RoomType.objects.all(),
        'selected_room_type': room_type_id,
        'selected_category': room_type_slug or '',
        'check_in_date': check_in_str or '',
        'check_out_date': check_out_str or '',
        'num_adults': num_adults or 1,
        'num_children': num_children or 0,
        'selected_max_price': max_price or '',
    }
    return render(request, 'publicsite/rooms.html', context)


def room_detail(request, pk):
    public_images = RoomTypeImage.objects.filter(is_published=True).order_by(
        '-is_featured', 'display_order', 'id'
    )
    room = get_object_or_404(
        Room.objects.select_related('room_type').prefetch_related('gallery_images',
            
            Prefetch('room_type__gallery_images', queryset=public_images, to_attr='public_gallery')
        ), pk=pk, is_active=True,
    )
    similar_rooms = Room.objects.select_related('room_type').filter(
        room_type=room.room_type,
        is_active=True,
    ).exclude(pk=room.pk)[:3]

    initial = {
        'room': room.id,
        'check_in_date': request.GET.get('check_in_date'),
        'check_out_date': request.GET.get('check_out_date'),
        'num_adults': request.GET.get('num_adults') or 1,
        'num_children': request.GET.get('num_children') or 0,
    }

    form = BookingRequestForm(request.POST or None, initial=initial)
    record_event(request, 'room_view', room_id=room.id, room_type_id=room.room_type_id)

    if request.method == 'POST':
        if not flag_enabled('public-booking', user=request.user, default=True):
            record_event(request, 'booking_error', error_code='feature_disabled')
            messages.error(request, 'Online booking is temporarily unavailable. Please contact the hotel.')
            return redirect('frontend:public-contact')

        form.data = form.data.copy()
        form.data['room'] = str(room.id)

        if form.is_valid():
            rate_plan = room.room_type.rate_plans.filter(is_active=True).first()
            if not rate_plan:
                record_event(request, 'booking_error', error_code='rate_unavailable')
                messages.error(request, 'No active rate is configured for this room.')
                return redirect('frontend:public-room-detail', pk=room.pk)
            try:
                quote = create_quote(
                    room=room,
                    rate_plan=rate_plan,
                    check_in_date=form.cleaned_data['check_in_date'],
                    check_out_date=form.cleaned_data['check_out_date'],
                    num_adults=form.cleaned_data['num_adults'],
                    num_children=form.cleaned_data['num_children'],
                    guest=request.user if request.user.is_authenticated else None,
                    email=form.cleaned_data['email'],
                    created_by=request.user if request.user.is_authenticated else None,
                    ttl_minutes=10,
                    promotion_code=form.cleaned_data.get('promotion_code', ''),
                    extras=form.cleaned_data.get('extras', []),
                )
            except ValidationError as exc:
                record_event(request, 'booking_error', error_code='quote_validation')
                messages.error(request, '; '.join(exc.messages))
                return redirect('frontend:public-room-detail', pk=room.pk)

            booking_data = {
                'first_name': form.cleaned_data['first_name'],
                'last_name': form.cleaned_data['last_name'],
                'email': form.cleaned_data['email'],
                'phone': form.cleaned_data['phone'],
                'check_in_date': form.cleaned_data['check_in_date'].isoformat(),
                'check_out_date': form.cleaned_data['check_out_date'].isoformat(),
                'room_id': room.id,
                'num_adults': form.cleaned_data['num_adults'],
                'num_children': form.cleaned_data['num_children'],
                'special_requests': form.cleaned_data['special_requests'],
                'extra_ids': [item.id for item in form.cleaned_data.get('extras', [])],
                'quote_id': quote.id,
            }
            request.session['pending_quote_booking'] = booking_data
            record_event(
                request, 'quote_created', quote_reference=str(quote.reference),
                room_id=room.id, room_type_id=room.room_type_id,
                promotion_code=form.cleaned_data.get('promotion_code', ''),
            )
            return redirect('frontend:public-quote-confirm')

    context = {
        'room': room,
        'similar_rooms': similar_rooms,
        'booking_form': form,
        'check_in_date': request.GET.get('check_in_date') or '',
        'check_out_date': request.GET.get('check_out_date') or '',
        'num_adults': request.GET.get('num_adults') or 1,
        'num_children': request.GET.get('num_children') or 0,
    }
    return render(request, 'publicsite/room-details.html', context)


def blog(request):
    return render(request, 'publicsite/blog.html')

def blog_detail(request):
    return render(request, 'publicsite/blog-details.html')


def public_faq(request):
    items = list(FAQItem.objects.filter(is_published=True))
    schema = json.dumps({
        '@context': 'https://schema.org', '@type': 'FAQPage',
        'mainEntity': [
            {
                '@type': 'Question', 'name': item.question,
                'acceptedAnswer': {'@type': 'Answer', 'text': item.answer},
            } for item in items
        ],
    }, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    categories = []
    for key, label in FAQItem.CATEGORY_CHOICES:
        category_items = [item for item in items if item.category == key]
        if category_items:
            categories.append((label, category_items))
    return render(request, 'publicsite/faq.html', {
        'faq_categories': categories, 'faq_schema_json': schema,
    })


def public_policies(request):
    policies = PolicyDocument.objects.filter(is_published=True).order_by('policy_type', 'title')
    return render(request, 'publicsite/policies.html', {'policies': policies})


def public_policy_detail(request, slug):
    policies = PolicyDocument.objects.filter(slug=slug)
    preview = bool(request.user.is_authenticated and request.user.is_staff and request.GET.get('preview') == '1')
    if not preview:
        policies = policies.filter(is_published=True)
    policy = get_object_or_404(policies)
    return render(request, 'publicsite/policy-detail.html', {'policy': policy, 'is_preview': preview})


def public_dining(request):
    categories = ServiceCategory.objects.prefetch_related('menu_items').all()
    return render(request, 'publicsite/dining.html', {'categories': categories})

def public_laundry(request):
    return render(request, 'publicsite/laundry.html')

def public_offers(request):
    now = timezone.now()
    promotions = Promotion.objects.filter(
        is_active=True,
        valid_from__lte=now,
        valid_to__gte=now,
    ).prefetch_related('room_types')

    offers = []
    for promo in promotions:
        discount_text = f"{promo.amount}% OFF" if promo.discount_type == 'percentage' else f"₦{promo.amount} OFF"
        room_types_str = ", ".join([rt.name for rt in promo.room_types.all()]) or "All Room Types"
        offers.append({
            'title': f"{promo.name} ({promo.code.upper()})",
            'description': promo.description or f"Use promo code {promo.code.upper()} to get {discount_text}. Valid for: {room_types_str}.",
            'price': discount_text,
            'code': promo.code,
            'capacity': f"Min stay {promo.minimum_nights} night(s)",
        })

    return render(
        request,
        'publicsite/offers.html',
        {
            'promotions': promotions,
            'offers': offers,
            'service_highlights': MenuItem.objects.filter(is_available=True).select_related('category')[:6],
        },
    )


def contact(request):
    form = ContactForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        case = create_inquiry(
            requester_name=form.cleaned_data['name'], requester_email=form.cleaned_data['email'],
            subject=form.cleaned_data['subject'], message=form.cleaned_data['message'],
            category=form.cleaned_data['category'],
            requester=request.user if request.user.is_authenticated else None,
        )
        messages.success(request, f'Thanks for contacting GRACEDAY INN. Your reference is {case.reference}.')
        return redirect('frontend:public-contact')
    return render(request, 'publicsite/contact.html', {'form': form})


def chat_start(request):
    if request.method != 'POST':
        return JsonResponse({'detail': 'POST required.'}, status=405)
    try:
        payload = json.loads(request.body or '{}')
    except ValueError:
        return JsonResponse({'detail': 'Invalid JSON.'}, status=400)
    body = (payload.get('message') or '').strip()
    if not body:
        return JsonResponse({'detail': 'A message is required.'}, status=400)
    guest = request.user if request.user.is_authenticated and request.user.role == 'guest' else None
    try:
        conversation = start_conversation(
            name=payload.get('name', guest.get_full_name() if guest else ''),
            email=payload.get('email', guest.email if guest else ''), guest=guest, body=body,
        )
    except ValidationError as exc:
        return JsonResponse({'errors': exc.messages}, status=400)
    tokens = request.session.get('chat_tokens', {})
    tokens[str(conversation.reference)] = str(conversation.visitor_token)
    request.session['chat_tokens'] = tokens
    return JsonResponse({
        'reference': str(conversation.reference),
        'status': conversation.status,
        'websocket_url': f'/ws/chat/{conversation.reference}/',
        'offline': conversation.is_offline_capture,
        'inquiry_reference': str(conversation.inquiry.reference) if conversation.inquiry_id else None,
    }, status=201)


def _public_chat_access(request, reference):
    conversation = get_object_or_404(ChatConversation, reference=reference)
    token = request.session.get('chat_tokens', {}).get(str(reference)) or request.GET.get('token')
    if not can_access_conversation(request.user, conversation, token):
        return conversation, None
    return conversation, token


def chat_messages(request, reference):
    conversation, token = _public_chat_access(request, reference)
    if token is None and not can_access_conversation(request.user, conversation):
        return JsonResponse({'detail': 'Access denied.'}, status=403)
    after = request.GET.get('after', 0)
    queryset = conversation.messages.filter(id__gt=after).exclude(sender_type='internal')[:100]
    return JsonResponse({'messages': [{
        'id': item.id, 'body': item.body, 'sender_type': item.sender_type,
        'created_at': item.created_at.isoformat(),
    } for item in queryset], 'status': conversation.status})


def chat_send(request, reference):
    if request.method != 'POST':
        return JsonResponse({'detail': 'POST required.'}, status=405)
    conversation, token = _public_chat_access(request, reference)
    if token is None and not can_access_conversation(request.user, conversation):
        return JsonResponse({'detail': 'Access denied.'}, status=403)
    try:
        payload = json.loads(request.body or '{}')
        message, created = send_chat_message(
            conversation=conversation, actor=request.user, visitor_token=token,
            body=payload.get('body', ''), client_message_id=payload.get('client_message_id'),
        )
    except (ValidationError, ValueError) as exc:
        return JsonResponse({'errors': getattr(exc, 'messages', [str(exc)])}, status=400)
    return JsonResponse({'id': message.id, 'created': created, 'sender_type': message.sender_type})


def chat_feedback(request, reference):
    if request.method != 'POST':
        return JsonResponse({'detail': 'POST required.'}, status=405)
    conversation, token = _public_chat_access(request, reference)
    if token is None and not can_access_conversation(request.user, conversation):
        return JsonResponse({'detail': 'Access denied.'}, status=403)
    try:
        payload = json.loads(request.body or '{}')
        submit_chat_satisfaction(
            conversation=conversation, rating=payload.get('rating'),
            comment=payload.get('comment', ''), actor=request.user, visitor_token=token,
        )
    except (ValidationError, ValueError) as exc:
        return JsonResponse({'errors': getattr(exc, 'messages', [str(exc)])}, status=400)
    return JsonResponse({'detail': 'Thank you for your feedback.'})


def portal_sign_in(request):
    if request.user.is_authenticated:
        return redirect(PORTAL_DASHBOARD_ROUTE)
    username = (request.POST.get('username') or '').strip() if request.method == 'POST' else ''
    blocked = request.method == 'POST' and login_is_blocked(request, username)
    form = PortalLoginForm(request, data=None if blocked else (request.POST or None))
    if blocked:
        record_authentication_event(request, 'portal_login_blocked', username=username)
    if request.method == 'POST' and not blocked and form.is_valid():
        user = form.get_user()
        clear_account_login_failures(user.username)
        if staff_mfa_required(user):
            request.session['pending_mfa_user_id'] = user.id
            request.session['pending_mfa_expires_at'] = int(timezone.now().timestamp()) + 300
            if StaffMFADevice.objects.filter(user=user, is_confirmed=True).exists():
                return redirect('frontend:portal-mfa-challenge')
            return redirect('frontend:portal-mfa-enroll')
        login(request, user)
        record_authentication_event(request, 'portal_login_success', user=user)
        messages.success(request, 'Welcome back to GRACEDAY INN portal.')
        return redirect(PORTAL_DASHBOARD_ROUTE)
    if request.method == 'POST' and not blocked and username:
        record_login_failure(request, username)
        record_authentication_event(request, 'portal_login_failed', username=username)
    return render(request, 'portals/sign-in.html', {
        'form': form,
        'blocked_error': 'Unable to sign in. Please wait and try again.' if blocked else '',
    })


def _pending_mfa_user(request):
    user_id = request.session.get('pending_mfa_user_id')
    expires_at = request.session.get('pending_mfa_expires_at', 0)
    if not user_id or expires_at < int(timezone.now().timestamp()):
        request.session.pop('pending_mfa_user_id', None)
        request.session.pop('pending_mfa_expires_at', None)
        return None
    return UserProfile.objects.filter(pk=user_id, is_active=True).first()


def _complete_mfa_login(request, user):
    login(request, user, backend='django.contrib.auth.backends.ModelBackend')
    request.session['staff_mfa_verified_user_id'] = user.id
    request.session['staff_mfa_verified_at'] = int(timezone.now().timestamp())
    request.session.pop('pending_mfa_user_id', None)
    request.session.pop('pending_mfa_expires_at', None)
    record_authentication_event(request, 'portal_login_success', user=user)


def portal_mfa_challenge(request):
    user = _pending_mfa_user(request)
    if not user:
        messages.error(request, 'The MFA login challenge expired. Sign in again.')
        return redirect('frontend:portal-sign-in')
    if request.method == 'POST':
        try:
            verify_mfa_code(user=user, code=request.POST.get('code', ''))
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
        else:
            _complete_mfa_login(request, user)
            messages.success(request, 'MFA verification completed.')
            return redirect(PORTAL_DASHBOARD_ROUTE)
    return render(request, 'portals/mfa.html', {'mode': 'challenge', 'mfa_user': user})


def portal_mfa_enroll(request):
    user = request.user if request.user.is_authenticated else _pending_mfa_user(request)
    if not user or user.role not in {'admin', 'manager', 'receptionist', 'housekeeping'}:
        messages.error(request, 'A valid staff sign-in is required for MFA enrollment.')
        return redirect('frontend:portal-sign-in')
    confirmed_device = StaffMFADevice.objects.filter(user=user, is_confirmed=True).first()
    if confirmed_device:
        if request.user.is_authenticated:
            return render(request, 'portals/mfa.html', {
                'mode': 'status', 'mfa_user': user, 'mfa_device': confirmed_device,
                'recovery_codes_remaining': len(confirmed_device.recovery_code_hashes),
            })
        return redirect('frontend:portal-mfa-challenge')
    try:
        _device, secret, provisioning_uri = begin_mfa_enrollment(user=user, actor=user)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
        return redirect(PORTAL_DASHBOARD_ROUTE if request.user.is_authenticated else 'frontend:portal-sign-in')
    if request.method == 'POST':
        try:
            _device, recovery_codes = confirm_mfa_enrollment(
                user=user, code=request.POST.get('code', ''), actor=user,
            )
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
        else:
            if not request.user.is_authenticated:
                _complete_mfa_login(request, user)
            return render(request, 'portals/mfa.html', {
                'mode': 'recovery', 'mfa_user': user, 'recovery_codes': recovery_codes,
            })
    return render(request, 'portals/mfa.html', {
        'mode': 'enroll', 'mfa_user': user, 'mfa_secret': secret,
        'provisioning_uri': provisioning_uri,
    })


def portal_sign_up(request):
    if request.user.is_authenticated:
        return redirect(PORTAL_DASHBOARD_ROUTE)
    form = PortalSignUpForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        GuestProfile.objects.get_or_create(user=user)
        login(request, user)
        messages.success(request, 'Your GRACEDAY INN account has been created.')
        return redirect(PORTAL_DASHBOARD_ROUTE)
    return render(request, 'portals/sign-up.html', {'form': form})


def portal_set_password(request, uidb64, token):
    try:
        user = UserProfile.objects.get(pk=force_str(urlsafe_base64_decode(uidb64)))
    except (TypeError, ValueError, OverflowError, UserProfile.DoesNotExist):
        user = None

    if not user or not default_token_generator.check_token(user, token):
        return render(request, 'portals/set-password.html', {'invalid_link': True}, status=400)

    form = SetPasswordForm(user, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        if staff_mfa_required(user):
            request.session['pending_mfa_user_id'] = user.id
            request.session['pending_mfa_expires_at'] = int(timezone.now().timestamp()) + 300
            record_authentication_event(request, 'password_setup_completed', user=user)
            return redirect('frontend:portal-mfa-enroll')
        login(request, user, backend='django.contrib.auth.backends.ModelBackend')
        record_authentication_event(request, 'password_setup_completed', user=user)
        messages.success(request, 'Your password has been set securely.')
        return redirect(PORTAL_DASHBOARD_ROUTE)
    return render(request, 'portals/set-password.html', {'form': form, 'invalid_link': False})


def portal_password_reset(request):
    if request.user.is_authenticated:
        return redirect(PORTAL_DASHBOARD_ROUTE)
    if request.method == 'POST':
        email = (request.POST.get('email') or '').strip().lower()
        if email:
            user = UserProfile.objects.filter(email__iexact=email, is_active=True).first()
            if user:
                token = default_token_generator.make_token(user)
                uidb64 = urlsafe_base64_encode(force_bytes(user.pk))
                reset_url = request.build_absolute_uri(
                    reverse('frontend:portal-set-password', kwargs={'uidb64': uidb64, 'token': token})
                )
                send_html_email(
                    subject='Reset Your GraceDay Inn Password',
                    template_name='emails/password_reset.html',
                    context={
                        'first_name': user.first_name or user.username,
                        'reset_url': reset_url,
                    },
                    recipient_list=[user.email],
                )
            messages.success(request, 'If an account exists with that email address, password reset instructions have been sent.')
            return redirect('frontend:portal-sign-in')
        messages.error(request, 'Please enter a valid email address.')
    return render(request, 'portals/password-reset.html')


@login_required
def portal_logout(request):
    logout(request)
    messages.info(request, 'You are signed out.')
    return redirect('frontend:portal-sign-in')


@login_required
def portal_dashboard(request):
    selected_days = _selected_window_days(request)
    trend_data = _build_trend_series(days=selected_days, user=request.user)

    recent_reservations = Reservation.objects.select_related('guest', 'room', 'room__room_type').order_by('-created_at')
    if request.user.role == 'guest':
        recent_reservations = recent_reservations.filter(guest=request.user)
    elif request.user.role == 'housekeeping':
        recent_reservations = recent_reservations.none()
    recent_reservations = recent_reservations[:5]

    # BUG-001 FIX: define recent_notifications (was undefined, causing NameError crash)
    recent_notifications = Notification.objects.filter(
        recipient=request.user,
    ).order_by('-created_at')[:8]

    stats = _portal_stats(request.user)

    context = {
        'stats': stats,
        'window_choices': sorted(list(ALLOWED_REPORT_WINDOWS)),
        'selected_days': selected_days,
        'recent_notifications': recent_notifications,
        'recent_reservations': recent_reservations,
        'trend_labels_json': json.dumps(trend_data['labels']),
        'occupancy_trend_json': json.dumps(trend_data['occupancy_trend']),
        'revenue_trend_json': json.dumps(trend_data['revenue_trend']),
        'service_sla_trend_json': json.dumps(trend_data['service_sla_trend']),
    }
    return render(request, 'portals/dashboard.html', context)


@login_required
@role_required({'guest', 'admin'})
def portal_my_stay(request):
    reservations = Reservation.objects.filter(guest=request.user).select_related(
        'room', 'room__room_type'
    ).prefetch_related('service_orders', 'companions').order_by('-check_in_date')
    active = reservations.filter(status__in=['confirmed', 'checked_in']).first()
    if request.method == 'POST':
        reservation = get_object_or_404(reservations, pk=request.POST.get('reservation'))
        request_type = request.POST.get('request_type', 'general')
        subject_map = {
            'change': 'Reservation change request', 'service': 'Guest service request',
            'billing': 'Billing assistance request', 'general': 'Guest assistance request',
        }
        case = create_inquiry(
            requester_name=request.user.get_full_name() or request.user.username,
            requester_email=request.user.email, requester=request.user,
            subject=f'{subject_map.get(request_type, subject_map["general"])} — {reservation.reservation_number}',
            message=request.POST.get('message', '').strip(),
            category='billing' if request_type == 'billing' else ('service' if request_type == 'service' else 'reservation'),
            source='guest_portal', reservation=reservation,
        )
        messages.success(request, f'Your request was submitted. Reference: {case.reference}.')
        return redirect('frontend:portal-my-stay')
    return render(request, 'portals/my-stay.html', {
        'reservations': reservations, 'active_reservation': active,
        'invoices': Invoice.objects.filter(guest=request.user).select_related('reservation').prefetch_related('receipts'),
        'payments': Payment.objects.filter(invoice__guest=request.user).select_related('receipt', 'invoice'),
        'folios': request.user.folios.select_related('reservation').prefetch_related('entries'),
        'inquiries': InquiryCase.objects.filter(requester=request.user).select_related('reservation')[:20],
    })


@login_required
def portal_privacy(request):
    is_manager = request.user.is_superuser or request.user.role in {'admin', 'manager'}
    if not is_manager and request.user.role != 'guest':
        return HttpResponse(status=403)
    if request.method == 'POST':
        command = request.POST.get('command', 'submit')
        try:
            if is_manager and command in {'approve', 'reject'}:
                review_privacy_request(
                    request_id=request.POST.get('request_id'), action=command,
                    actor=request.user, reason=request.POST.get('reason', ''),
                )
            elif is_manager and command == 'execute':
                execute_privacy_request(
                    request_id=request.POST.get('request_id'), actor=request.user,
                )
            elif not is_manager and command == 'submit':
                submit_privacy_request(
                    guest=request.user, request_type=request.POST.get('request_type'),
                    details=request.POST.get('details', ''),
                )
            else:
                raise ValidationError('Unknown privacy workflow command.')
        except (ValidationError, ValueError, TypeError, DataPrivacyRequest.DoesNotExist) as exc:
            messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
        else:
            messages.success(request, 'Privacy request updated with an immutable history event.')
        return redirect('frontend:portal-privacy')
    items = DataPrivacyRequest.objects.select_related('guest', 'reviewed_by').prefetch_related('history')
    if not is_manager:
        items = items.filter(guest=request.user)
    return render(request, 'portals/privacy.html', {
        'privacy_requests': items, 'is_privacy_manager': is_manager,
        'request_types': DataPrivacyRequest.TYPE_CHOICES,
    })


@login_required
def portal_privacy_download(request, pk):
    item = get_object_or_404(DataPrivacyRequest.objects.select_related('guest'), pk=pk)
    is_manager = request.user.is_superuser or request.user.role in {'admin', 'manager'}
    if not is_manager and item.guest_id != request.user.id:
        return HttpResponse(status=403)
    if not item.artifact or not item.artifact_expires_at or item.artifact_expires_at <= timezone.now():
        raise Http404('This privacy export is unavailable or expired.')
    return FileResponse(
        item.artifact.open('rb'), as_attachment=True,
        filename=f'gracedayinn-privacy-export-{item.reference}.json',
        content_type='application/json',
    )


@login_required
def portal_rooms(request):
    can_manage_rooms = request.user.role in STAFF_ROLES
    can_manage_sales_inventory = request.user.is_superuser or request.user.role in {'admin', 'manager'}
    room_form = None
    room_type_form = None
    amenity_form = None
    if can_manage_rooms:
        if request.method == 'POST':
            command = request.POST.get('command', '')
            if command == 'create_room_type':
                room_type_form = RoomTypeCreateForm(request.POST, request.FILES)
                if room_type_form.is_valid():
                    room_type_form.save()
                    messages.success(request, 'Room category created. You can now assign rooms to it.')
                    return redirect('frontend:portal-rooms')
            elif command == 'create_inventory_block' and can_manage_sales_inventory:
                try:
                    create_inventory_block(
                        room=Room.objects.get(pk=request.POST.get('room_id')),
                        start_date=request.POST.get('start_date'), end_date=request.POST.get('end_date'),
                        reason=request.POST.get('reason', 'other'), notes=request.POST.get('notes', ''),
                        actor=request.user,
                    )
                except (ValidationError, ValueError, TypeError, Room.DoesNotExist) as exc:
                    messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
                else:
                    messages.success(request, 'Date-bound sales block created.')
                return redirect('frontend:portal-rooms')
            elif command == 'release_inventory_block' and can_manage_sales_inventory:
                try:
                    release_inventory_block(block_id=request.POST.get('block_id'), actor=request.user)
                except (ValidationError, ValueError, TypeError) as exc:
                    messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
                else:
                    messages.success(request, 'Sales block released.')
                return redirect('frontend:portal-rooms')
            elif 'amenity_submit' in request.POST:
                amenity_form = AmenityCreateForm(request.POST)
                if amenity_form.is_valid():
                    amenity = amenity_form.save()
                    messages.success(request, f'Amenity {amenity.name} created successfully.')
                    return redirect('frontend:portal-rooms')
            else:
                room_form = RoomCreateForm(request.POST, request.FILES)
                if room_form.is_valid():
                    room = room_form.save()
                    for image in request.FILES.getlist('gallery_images'):
                        RoomImage.objects.create(room=room, image=image, alt_text=f'Room {room.number}')
                    messages.success(request, f'Room {room.number} created successfully.')
                    return redirect('frontend:portal-rooms')
        else:
            room_form = RoomCreateForm()
            amenity_form = AmenityCreateForm()

    rooms = Room.objects.select_related('room_type').all()
    return render(
        request,
        'portals/tables.html',
        {
            'rooms': rooms,
            'stats': _portal_stats(request.user),
            'room_form': room_form,
            'room_type_form': room_type_form or RoomTypeCreateForm(),
            'amenity_form': amenity_form,
            'can_manage_rooms': can_manage_rooms,
            'can_manage_sales_inventory': can_manage_sales_inventory,
            'inventory_blocks': InventoryBlock.objects.filter(status='active').select_related('room', 'created_by'),
        },
    )

# =========================================================
# ROOM MANAGEMENT
# =========================================================

@login_required
def portal_room_detail(request, pk):
    """
    Display details for a single room.
    """
    room = get_object_or_404(
        Room.objects.select_related('room_type').prefetch_related('gallery_images', 'amenities', 'room_type__gallery_images'),
        pk=pk,
    )

    recent_reservations = Reservation.objects.filter(
        room=room
    ).select_related(
        'guest'
    ).order_by('-created_at')[:10]
    if request.user.role == 'guest':
        recent_reservations = Reservation.objects.filter(
            room=room, guest=request.user
        ).select_related('guest').order_by('-created_at')[:10]
    elif request.user.role == 'housekeeping':
        recent_reservations = Reservation.objects.none()

    # Provide a reservation form for the modal on the room detail page.
    reservation_form = PortalReservationForm()

    return render(
        request,
        'portals/room-detail.html',
        {
            'room': room,
            'recent_reservations': recent_reservations,
            'stats': _portal_stats(request.user),
            'reservation_form': reservation_form,
        },
    )


@login_required
@role_required({'admin', 'manager', 'receptionist', 'guest'})
def portal_room_reserve(request, pk):
    """
    Reserve a room directly.
    Guests reserve for themselves.
    Staff may reserve for any guest.
    """

    room = get_object_or_404(
        Room,
        pk=pk,
        is_active=True,
    )

    if room.status != 'available':
        messages.error(
            request,
            'This room is currently unavailable.'
        )
        return redirect(
            'frontend:portal-room-detail',
            pk=room.pk,
        )

    form = PortalReservationForm(
        request.POST or None
    )

    if request.method == 'POST' and form.is_valid():

        data = form.cleaned_data
        reservation_guest = request.user if request.user.role == 'guest' else data['guest']
        try:
            reservation = create_reservation(
                guest=reservation_guest,
                room=room,
                check_in_date=data['check_in_date'],
                check_out_date=data['check_out_date'],
                num_adults=data['num_adults'],
                num_children=data['num_children'],
                special_requests=data['special_requests'],
                created_by=request.user,
                source='front_desk',
            )
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
            return redirect('frontend:portal-room-detail', pk=room.pk)

        _notify_user(
            recipient=reservation.guest,
            title='Reservation Created',
            message=(
                f'Your reservation '
                f'{reservation.reservation_number} '
                'has been created successfully.'
            ),
            notification_type='reservation',
            link=RESERVATIONS_LINK,
        )

        _notify_staff(
            title='New Reservation',
            message=(
                f'Room {room.number} has been reserved by '
                f'{reservation.guest.get_full_name()}.'
            ),
            notification_type='reservation',
            link=RESERVATIONS_LINK,
        )

        _log_audit(
            request,
            event_type='reservation',
            action='create_reservation',
            target_model='Reservation',
            target_id=reservation.id,
            details={
                'reservation_number': reservation.reservation_number,
                'room_number': room.number,
            },
        )

        messages.success(
            request,
            f'Room {room.number} reserved successfully.'
        )

        return redirect(PORTAL_RESERVATIONS_ROUTE)

    return render(
        request,
        'portals/room-reserve.html',
        {
            'room': room,
            'form': form,
            'stats': _portal_stats(request.user),
        },
    )


@login_required
@role_required({'admin', 'manager', 'receptionist'})
def portal_room_edit(request, pk):
    """
    Edit an existing room.
    """

    room = get_object_or_404(
        Room,
        pk=pk,
    )

    form = RoomCreateForm(
        request.POST or None,
        request.FILES or None,
        instance=room,
    )

    if request.method == 'POST' and form.is_valid():

        room = form.save()
        for image in request.FILES.getlist('gallery_images'):
            RoomImage.objects.create(room=room, image=image, alt_text=f'Room {room.number}')

        _log_audit(
            request,
            event_type='system',
            action='edit_room',
            target_model='Room',
            target_id=room.id,
            details={
                'room_number': room.number,
            },
        )

        messages.success(
            request,
            f'Room {room.number} updated successfully.'
        )

        return redirect('frontend:portal-rooms')

    return render(
        request,
        'portals/room-edit.html',
        {
            'room': room,
            'editable_rooms': Room.objects.filter(is_active=True).select_related('room_type').order_by('number'),
            'form': form,
            'stats': _portal_stats(request.user),
        },
    )


@login_required
@role_required({'admin', 'manager'})
def portal_room_delete(request, pk):
    """
    Deactivate a room instead of permanently deleting it.
    """

    room = get_object_or_404(
        Room,
        pk=pk,
    )

    if request.method == 'POST':

        room.is_active = False

        room.save(
            update_fields=['is_active']
        )

        _log_audit(
            request,
            event_type='system',
            action='deactivate_room',
            target_model='Room',
            target_id=room.id,
            details={
                'room_number': room.number,
            },
        )

        messages.success(
            request,
            f'Room {room.number} has been deactivated.'
        )

        return redirect('frontend:portal-rooms')

    return render(
        request,
        'portals/room-delete.html',
        {
            'room': room,
            'stats': _portal_stats(request.user),
        },
    )

@login_required
def portal_reservations(request):
    can_manage = request.user.role in STAFF_ROLES
    reservation_form = None
    if can_manage:
        reservation_form = PortalReservationForm(request.POST or None)
        if request.method == 'POST' and reservation_form.is_valid():
            data = reservation_form.cleaned_data
            try:
                reservation = create_reservation(
                    guest=data['guest'], room=data['room'],
                    check_in_date=data['check_in_date'], check_out_date=data['check_out_date'],
                    num_adults=data['num_adults'], num_children=data['num_children'],
                    special_requests=data['special_requests'], created_by=request.user,
                    source='front_desk',
                )
            except ValidationError as exc:
                messages.error(request, '; '.join(exc.messages))
                return redirect(PORTAL_RESERVATIONS_ROUTE)
            _notify_user(
                recipient=reservation.guest,
                title='Reservation created',
                message=f'Your reservation {reservation.reservation_number} has been created and is pending confirmation.',
                notification_type='reservation',
                link=RESERVATIONS_LINK,
            )
            messages.success(request, f'Reservation {reservation.reservation_number} created successfully.')
            return redirect(PORTAL_RESERVATIONS_ROUTE)


    reservations = Reservation.objects.select_related('guest', 'room', 'room__room_type', 'invoice').order_by('-created_at')
    if request.user.role == 'guest':
        reservations = reservations.filter(guest=request.user)
        
    room_prices = {}
    if can_manage:
        import json
        for r in Room.objects.filter(is_active=True, is_sellable=True):
            room_prices[r.id] = float(r.current_price)
            
    return render(
        request,
        'portals/reservations.html',
        {
            'reservations': reservations,
            'stats': _portal_stats(request.user),
            'reservation_form': reservation_form,
            'can_manage_reservations': can_manage,
            'room_prices_json': json.dumps(room_prices),
        },
    )



@login_required
@action_role_required(
    {
        'confirm': {'admin', 'manager', 'receptionist'},
        'check_in': {'admin', 'manager', 'receptionist'},
        'check_out': {'admin', 'manager', 'receptionist'},
        'cancel': {'admin', 'manager', 'receptionist', 'guest'},
        'no_show': {'admin', 'manager', 'receptionist'},
    },
    redirect_route=PORTAL_RESERVATIONS_ROUTE,
)
def portal_reservation_action(request, pk, action):
    if request.method != 'POST':
        return redirect(PORTAL_RESERVATIONS_ROUTE)

    reservation = get_object_or_404(Reservation.objects.select_related('invoice'), pk=pk)
    if action == 'cancel' and request.user.role == 'guest' and reservation.guest_id != request.user.id:
        messages.error(request, 'Guests can only cancel their own reservations.')
        return redirect(PORTAL_RESERVATIONS_ROUTE)
    if action == 'confirm':
        invoice = getattr(reservation, 'invoice', None)
        if not invoice or invoice.total <= 0 or invoice.amount_paid < (invoice.total * Decimal('0.50')):
            messages.error(request, 'At least a 50% payment is required before confirming this reservation.')
            return redirect(f'{PORTAL_PAYMENTS_ROUTE}?invoice_id={invoice.id}' if invoice else PORTAL_RESERVATIONS_ROUTE)

    try:
        reservation = transition_reservation(
            reservation_id=reservation.pk, action=action, actor=request.user
        )
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
        return redirect(PORTAL_RESERVATIONS_ROUTE)
    _log_audit(
        request,
        event_type='reservation',
        action=f'reservation_{action}',
        target_model='Reservation',
        target_id=reservation.id,
        details={'reservation_number': reservation.reservation_number, 'new_status': reservation.status},
    )
    messages.success(request, f'Reservation {reservation.reservation_number} updated to {reservation.status}.')
    return redirect(PORTAL_RESERVATIONS_ROUTE)


@login_required
@role_required(STAFF_ROLES)
def portal_front_desk(request):
    business_date = timezone.localdate()
    base = Reservation.objects.select_related('guest', 'room', 'room__room_type', 'invoice')
    search_query = request.GET.get('q', '').strip()[:100]
    if search_query:
        base = base.filter(
            Q(reservation_number__icontains=search_query)
            | Q(guest__username__icontains=search_query)
            | Q(guest__first_name__icontains=search_query)
            | Q(guest__last_name__icontains=search_query)
            | Q(guest__phone__icontains=search_query)
            | Q(room__number__icontains=search_query)
        )
    arrivals = base.filter(check_in_date=business_date, status='confirmed').order_by('room__number')
    in_house = base.filter(status='checked_in').order_by('room__number')
    departures = base.filter(check_out_date=business_date, status='checked_in').order_by('room__number')
    pending = base.filter(status='pending', check_in_date__lte=business_date).order_by('check_in_date')
    rooms = Room.objects.select_related('room_type').filter(is_active=True).order_by('number')
    room_counts = rooms.values('status').annotate(total=Count('id'))
    return render(request, 'portals/front-desk.html', {
        'business_date': business_date,
        'arrivals': arrivals,
        'in_house': in_house,
        'departures': departures,
        'pending': pending,
        'rooms': rooms,
        'room_counts': {row['status']: row['total'] for row in room_counts},
        'search_query': search_query,
    })


@login_required
@role_required(STAFF_ROLES)
def portal_tape_chart(request):
    start = timezone.localdate()
    requested = request.GET.get('start')
    if requested:
        try:
            start = timezone.datetime.strptime(requested, '%Y-%m-%d').date()
        except ValueError:
            pass
    dates = [start + timedelta(days=index) for index in range(14)]
    reservations = Reservation.objects.select_related('guest', 'room').filter(
        status__in=['pending', 'confirmed', 'checked_in'],
        check_in_date__lt=dates[-1] + timedelta(days=1), check_out_date__gt=start,
    )
    room_rows = []
    for room in Room.objects.select_related('room_type').filter(is_active=True).order_by('number'):
        room_bookings = list(reservations.filter(room=room))
        room_rows.append({
            'room': room,
            'cells': [next((item for item in room_bookings if item.check_in_date <= day < item.check_out_date), None) for day in dates],
        })
    return render(request, 'portals/tape-chart.html', {
        'dates': dates, 'room_rows': room_rows, 'start': start,
        'previous_start': start - timedelta(days=14), 'next_start': start + timedelta(days=14),
    })


@login_required
@role_required(STAFF_ROLES)
def portal_commercial(request):
    if request.method == 'POST':
        command = request.POST.get('command')
        try:
            if command == 'corporate_create':
                if request.user.role not in {'admin', 'manager'} and not request.user.is_superuser:
                    raise ValidationError('Only managers or administrators can create corporate accounts.')
                CorporateAccount.objects.create(
                    name=request.POST.get('name', '').strip(),
                    account_code=request.POST.get('account_code', '').strip().lower(),
                    billing_email=request.POST.get('billing_email', '').strip().lower(),
                    phone=request.POST.get('phone', '').strip(),
                    credit_limit=Decimal(request.POST.get('credit_limit') or '0'),
                    payment_terms_days=int(request.POST.get('payment_terms_days') or 0),
                )
            elif command == 'group_create':
                account_id = request.POST.get('corporate_account')
                group = GroupBooking(
                    name=request.POST.get('name', '').strip(),
                    corporate_account=CorporateAccount.objects.filter(pk=account_id).first() if account_id else None,
                    arrival_date=parse_date(request.POST.get('arrival_date', '')),
                    departure_date=parse_date(request.POST.get('departure_date', '')),
                    room_target=int(request.POST.get('room_target') or 1),
                    status='open', created_by=request.user,
                    notes=request.POST.get('notes', '').strip(),
                )
                group.full_clean()
                group.save()
            elif command == 'discount_request':
                request_reservation_discount(
                    reservation_id=int(request.POST.get('reservation')),
                    amount=request.POST.get('amount'), reason=request.POST.get('reason', ''),
                    actor=request.user,
                )
            elif command in {'discount_approve', 'discount_reject'}:
                review_reservation_discount(
                    request_id=int(request.POST.get('discount_request')),
                    action='approve' if command == 'discount_approve' else 'reject',
                    actor=request.user, note=request.POST.get('note', ''),
                )
            else:
                raise ValidationError('Unknown commercial command.')
        except (ValidationError, ValueError, TypeError, InvalidOperation) as exc:
            detail = '; '.join(getattr(exc, 'messages', [])) or str(exc)
            messages.error(request, detail)
        else:
            messages.success(request, 'Commercial record updated successfully.')
        return redirect('frontend:portal-commercial')

    return render(request, 'portals/commercial.html', {
        'corporate_accounts': CorporateAccount.objects.all()[:100],
        'group_bookings': GroupBooking.objects.select_related('corporate_account').all()[:100],
        'active_reservations': Reservation.objects.select_related('guest').filter(
            status__in=['pending', 'confirmed', 'checked_in']
        )[:200],
        'discount_requests': ReservationDiscountRequest.objects.select_related(
            'reservation', 'requested_by', 'reviewed_by'
        ).all()[:100],
        'can_approve': request.user.is_superuser or request.user.role in {'admin', 'manager'},
    })


@login_required
@role_required(STAFF_ROLES)
def portal_reservation_manage(request, pk):
    reservation = get_object_or_404(
        Reservation.objects.select_related('guest', 'room', 'rate_plan').prefetch_related(
            'companions', 'amendments', 'room_assignments'
        ), pk=pk,
    )
    if request.method == 'POST':
        command = request.POST.get('command')
        try:
            if command == 'move':
                target = get_object_or_404(Room, pk=request.POST.get('room'))
                reservation = move_reservation_room(
                    reservation_id=reservation.id, new_room=target, actor=request.user,
                    reason=request.POST.get('reason', 'Room move'),
                )
            elif command == 'amend':
                reservation = amend_reservation_stay(
                    reservation_id=reservation.id,
                    check_in_date=timezone.datetime.strptime(request.POST['check_in_date'], '%Y-%m-%d').date(),
                    check_out_date=timezone.datetime.strptime(request.POST['check_out_date'], '%Y-%m-%d').date(),
                    num_adults=int(request.POST.get('num_adults', 1)),
                    num_children=int(request.POST.get('num_children', 0)),
                    actor=request.user, reason=request.POST.get('reason', 'Stay amendment'),
                )
            elif command == 'companion':
                if reservation.companions.count() >= max(reservation.num_adults + reservation.num_children - 1, 0):
                    raise ValidationError('Companion count would exceed the reservation occupancy.')
                GuestCompanion.objects.create(
                    reservation=reservation, full_name=request.POST.get('full_name', '').strip(),
                    email=request.POST.get('email', '').strip(), phone=request.POST.get('phone', '').strip(),
                    nationality=request.POST.get('nationality', '').strip(),
                    identity_type=request.POST.get('identity_type', '').strip(),
                    identity_last_four=request.POST.get('identity_last_four', '').strip()[-4:],
                    is_child=request.POST.get('is_child') == 'on',
                )
            elif command == 'consent':
                GuestConsentHistory.objects.create(
                    guest=reservation.guest, purpose=request.POST.get('purpose', '').strip(),
                    wording_version=request.POST.get('wording_version', '').strip(),
                    granted=request.POST.get('granted') == 'on', source='front_desk', actor=request.user,
                    metadata={'reservation_id': reservation.id},
                )
            else:
                raise ValidationError('Unknown reservation management command.')
        except (ValidationError, ValueError, KeyError) as exc:
            messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
        else:
            messages.success(request, 'Reservation record updated.')
        return redirect('frontend:portal-reservation-manage', pk=reservation.id)
    available_rooms = Room.objects.select_related('room_type').filter(is_active=True).exclude(pk=reservation.room_id)
    return render(request, 'portals/reservation-manage.html', {
        'reservation': reservation, 'available_rooms': available_rooms,
        'consents': reservation.guest.consent_history.all(),
    })

@login_required
@role_required({'admin', 'manager', 'receptionist'})
def portal_guests(request):
    from apps.accounts.guests import duplicate_guest_groups, merge_guest_accounts
    guests = UserProfile.objects.filter(role='guest', merged_into__isnull=True).order_by('first_name', 'last_name')
    command = request.POST.get('command', 'create_guest')
    guest_form = GuestCreateForm(request.POST or None) if command == 'create_guest' else GuestCreateForm()

    if request.method == 'POST':
        if command == 'merge_guest':
            try:
                merge_guest_accounts(
                    primary_id=int(request.POST.get('primary_id', '')),
                    duplicate_id=int(request.POST.get('duplicate_id', '')),
                    actor=request.user,
                    reason=request.POST.get('reason', ''),
                )
            except (ValidationError, ValueError, TypeError) as exc:
                messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
            else:
                messages.success(request, 'Guest records merged. All linked operational records were transferred.')
            return redirect('frontend:portal-guests')
        if guest_form.is_valid():
            guest_form.save()
            messages.success(request, 'Guest account created successfully.')
            return redirect('frontend:portal-guests')

    return render(
        request,
        'portals/guests.html',
        {
            'guests': guests,
            'stats': _portal_stats(request.user),
            'guest_form': guest_form,
            'duplicate_guests': duplicate_guest_groups(),
            'can_merge_guests': request.user.is_superuser or request.user.role in {'admin', 'manager'},
        },
    )

# =========================================================
# STAFF MANAGEMENT
# =========================================================

@login_required
@role_required({'admin', 'manager'})
def portal_staff(request):
    staff_roles = {
        'admin',
        'manager',
        'receptionist',
        'housekeeping',
        'accountant',
    }

    if request.method == 'POST' and request.user.role != 'admin' and not request.user.is_superuser:
        messages.error(request, 'Only administrators can create staff accounts.')
        return redirect('frontend:portal-staff')

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip().lower()
        phone = request.POST.get('phone', '').strip()
        role = request.POST.get('role', '').strip()

        if role not in staff_roles:
            messages.error(request, 'Invalid staff role selected.')
            return redirect('frontend:portal-staff')

        if not first_name or not last_name or not email:
            messages.error(
                request,
                'First name, last name and email are required.'
            )
            return redirect('frontend:portal-staff')

        if UserProfile.objects.filter(email=email).exists():
            messages.error(
                request,
                'A user with this email already exists.'
            )
            return redirect('frontend:portal-staff')

        base_username = email.split('@')[0] or 'staff'
        username = base_username
        counter = 1

        while UserProfile.objects.filter(username=username).exists():
            username = f'{base_username}{counter}'
            counter += 1

        staff = UserProfile.objects.create(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            role=role,
            is_active=True,
        )

        staff.set_unusable_password()
        staff.save()

        staff_uid = urlsafe_base64_encode(force_bytes(staff.pk))
        staff_token = default_token_generator.make_token(staff)
        staff_setup_url = request.build_absolute_uri(
            reverse('frontend:portal-set-password', args=[staff_uid, staff_token])
        )
        invitation_sent = send_html_email(
            subject='GRACEDAY INN - Set up your staff account',
            template_name='emails/staff_invite.html',
            context={
                'first_name': staff.first_name,
                'role': staff.get_role_display(),
                'username': staff.username,
                'setup_url': staff_setup_url,
            },
            recipient_list=[staff.email],
        )

        _log_audit(
            request,
            event_type='security',
            action='create_staff',
            target_model='UserProfile',
            target_id=staff.id,
            details={
                'username': staff.username,
                'email': staff.email,
                'role': staff.role,
            },
        )

        if invitation_sent:
            messages.success(request, f'Staff account for {staff.get_full_name()} created and invitation sent.')
        else:
            messages.warning(request, f'Staff account for {staff.get_full_name()} was created, but the invitation could not be sent.')

        return redirect('frontend:portal-staff')

    staff_members = UserProfile.objects.filter(
        role__in=staff_roles
    ).order_by('first_name', 'last_name')

    staff_role_options = [
        ('admin', 'Admin'),
        ('manager', 'Manager'),
        ('receptionist', 'Receptionist'),
        ('housekeeping', 'Housekeeping'),
        ('accountant', 'Accountant'),
    ]

    return render(
        request,
        'portals/staff.html',
        {
            'staff': staff_members,
            'staff_members': staff_members,
            'staff_roles': sorted(staff_roles),
            'staff_role_options': staff_role_options,
            'can_manage_staff': request.user.is_superuser or request.user.role == 'admin',
            'stats': _portal_stats(request.user),
        },
    )


@login_required
@action_role_required({
    'activate': {'admin'}, 'deactivate': {'admin'}, 'delete': {'admin'},
    'resend_invite': {'admin'},
}, redirect_route='frontend:portal-staff')
def portal_staff_action(request, pk, action):
    if request.method != 'POST':
        return redirect('frontend:portal-staff')

    staff = get_object_or_404(
        UserProfile,
        pk=pk,
        role__in={
            'admin',
            'manager',
            'receptionist',
            'housekeeping',
        },
    )

    if staff.pk == request.user.pk:
        messages.error(
            request,
            'You cannot perform this action on your own account.'
        )
        return redirect('frontend:portal-staff')

    if action == 'activate':
        staff.is_active = True
        staff.save(update_fields=['is_active'])
        messages.success(
            request,
            f'{staff.get_full_name()} has been activated.'
        )

    elif action == 'deactivate':
        staff.is_active = False
        staff.save(update_fields=['is_active'])
        messages.success(
            request,
            f'{staff.get_full_name()} has been deactivated.'
        )

    elif action == 'delete':
        name = staff.get_full_name()
        staff.is_active = False
        staff.save(update_fields=['is_active'])
        messages.success(
            request,
            f'{name} has been retired and retained for audit integrity.'
        )

    elif action == 'resend_invite':
        staff_uid = urlsafe_base64_encode(force_bytes(staff.pk))
        staff_token = default_token_generator.make_token(staff)
        staff_setup_url = request.build_absolute_uri(
            reverse('frontend:portal-set-password', args=[staff_uid, staff_token])
        )
        invitation_sent = send_html_email(
            subject='GRACEDAY INN - Set up your staff account',
            template_name='emails/staff_invite.html',
            context={
                'first_name': staff.first_name,
                'role': staff.get_role_display(),
                'username': staff.username,
                'setup_url': staff_setup_url,
            },
            recipient_list=[staff.email],
        )
        if invitation_sent:
            messages.success(request, f'Invitation resent to {staff.get_full_name()} ({staff.email}).')
        else:
            messages.error(request, f'Could not send invitation email to {staff.email}.')

    else:
        messages.error(request, 'Unknown staff action.')

    _log_audit(
        request,
        event_type='security',
        action=f'staff_{action}',
        target_model='UserProfile',
        target_id=staff.id,
        details={'username': staff.username, 'role': staff.role},
    )

    return redirect('frontend:portal-staff')


# =========================================================
# NEWSLETTER MANAGEMENT
# =========================================================

@login_required
@role_required({'admin', 'manager'})
def portal_newsletter(request):
    subscribers = NewsletterSubscription.objects.all().order_by('-id')
    newsletter_form = NewsletterMessageForm(request.POST or None, request.FILES or None)

    if request.method == 'POST' and newsletter_form.is_valid():
        newsletter_form.save()
        messages.success(request, 'Newsletter draft saved successfully.')
        return redirect('frontend:portal-newsletter')

    messages_list = NewsletterMessage.objects.order_by('-created_at')[:10]

    return render(
        request,
        'portals/newsletter.html',
        {
            'subscribers': subscribers,
            'newsletter_form': newsletter_form,
            'newsletters': messages_list,
            'stats': _portal_stats(request.user),
        },
    )


@login_required
@action_role_required({
    'activate': {'admin', 'manager'}, 'deactivate': {'admin', 'manager'},
    'delete': {'admin', 'manager'},
}, redirect_route='frontend:portal-newsletter')
def portal_newsletter_action(request, pk, action):
    if request.method != 'POST':
        return redirect('frontend:portal-newsletter')

    subscriber = get_object_or_404(
        NewsletterSubscription,
        pk=pk,
    )

    if action == 'activate':
        if Suppression.objects.filter(email__iexact=subscriber.email).exists():
            messages.error(request, 'This address is suppressed and cannot be reactivated here.')
            return redirect('frontend:portal-newsletter')
        subscriber.is_active = True
        subscriber.save(update_fields=['is_active'])
        ContactPreference.objects.update_or_create(
            email=subscriber.email, purpose='marketing', defaults={
                'consent_granted': True, 'consent_source': 'admin_reactivation',
                'granted_at': timezone.now(), 'withdrawn_at': None,
            },
        )
        messages.success(
            request,
            f'{subscriber.email} has been activated.'
        )

    elif action == 'deactivate':
        subscriber.is_active = False
        subscriber.save(update_fields=['is_active'])
        ContactPreference.objects.update_or_create(
            email=subscriber.email, purpose='marketing', defaults={
                'consent_granted': False, 'consent_source': 'admin_deactivation',
                'withdrawn_at': timezone.now(),
            },
        )
        Suppression.objects.update_or_create(
            email=subscriber.email, defaults={'reason': 'manual', 'source': 'portal'}
        )
        messages.success(
            request,
            f'{subscriber.email} has been unsubscribed.'
        )

    elif action == 'delete':
        email = subscriber.email
        subscriber.is_active = False
        subscriber.save(update_fields=['is_active'])
        messages.success(
            request,
            f'{email} has been removed from the newsletter list.'
        )

    else:
        messages.error(request, 'Unknown newsletter action.')

    return redirect('frontend:portal-newsletter')


@login_required
@role_required({'admin', 'manager'})
def portal_newsletter_send(request, pk):
    if request.method != 'POST':
        return redirect('frontend:portal-newsletter')
    newsletter = get_object_or_404(NewsletterMessage, pk=pk)
    if newsletter.status != 'ready_to_send':
        messages.error(request, 'Only an approved ready-to-send newsletter can be dispatched.')
        return redirect('frontend:portal-newsletter')
    recipients = NewsletterSubscription.objects.filter(is_active=True).exclude(
        email__in=Suppression.objects.values('email')
    )
    html = render_to_string('emails/newsletter.html', {'newsletter': newsletter})
    text = strip_tags(html)
    sent = 0
    for subscription in recipients.iterator():
        message, _ = enqueue_email(
            purpose='newsletter', recipient_email=subscription.email,
            subject=newsletter.subject, html_body=html, text_body=text, marketing=True,
            related_model='NewsletterMessage', related_id=newsletter.id,
            idempotency_key=f'newsletter:{newsletter.id}:{subscription.email.lower()}',
        )
        if message.status in {'queued', 'accepted'}:
            sent += 1
    newsletter.status, newsletter.sent_at, newsletter.recipient_count = 'sent', timezone.now(), sent
    newsletter.save(update_fields=['status', 'sent_at', 'recipient_count', 'updated_at'])
    messages.success(request, f'Newsletter queued for {sent} subscribed recipient(s).')
    return redirect('frontend:portal-newsletter')


@login_required
@role_required({'admin', 'manager', 'receptionist', 'guest'})
def portal_billing(request):
    invoices = Invoice.objects.select_related('guest', 'reservation').order_by('-created_at')
    if request.user.role == 'guest':
        invoices = invoices.filter(guest=request.user)
    can_correct = request.user.is_superuser or request.user.role in {'admin', 'manager'}
    if request.method == 'POST':
        if not can_correct:
            return HttpResponse(status=403)
        try:
            correction = post_financial_correction(
                folio_id=request.POST.get('folio_id'), kind=request.POST.get('kind'),
                amount=request.POST.get('amount'), reason=request.POST.get('reason', ''),
                actor=request.user,
            )
        except (ValidationError, ValueError, TypeError, Folio.DoesNotExist) as exc:
            messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
        else:
            _log_audit(
                request, event_type='payment', action=f'folio_{correction.kind}',
                target_model='FinancialCorrection', target_id=correction.id,
                details={'folio_id': correction.folio_id, 'amount': str(correction.entry.amount), 'reason': correction.reason},
            )
            messages.success(request, f'{correction.get_kind_display()} posted as an immutable compensating entry.')
        return redirect('frontend:portal-billing')
    summary = tax_summary(
        start_date=parse_date(request.GET.get('start_date', '')),
        end_date=parse_date(request.GET.get('end_date', '')),
    )
    return render(request, 'portals/billing.html', {
        'invoices': invoices, 'stats': _portal_stats(request.user),
        'folios': Folio.objects.select_related('guest', 'reservation').filter(status='open') if can_correct else [],
        'can_correct': can_correct, 'tax_summary': summary,
    })


@login_required
@role_required({'admin', 'manager', 'receptionist', 'guest'})
def portal_invoice_receipt(request, invoice_id):
    """Render a printable receipt view for an invoice supporting both A4 and POS thermal formats."""
    invoice = Invoice.objects.prefetch_related('items').select_related('guest', 'reservation').filter(pk=invoice_id).first()
    if not invoice:
        return HttpResponse(status=404)
    if request.user.role == 'guest' and invoice.guest_id != request.user.id:
        return HttpResponse(status=403)
    
    fmt = request.GET.get('format', 'a4').lower()
    if fmt in ('pos', 'thermal', 'slip'):
        receipt = invoice.receipts.first()
        payment = invoice.payments.first()
        return render(request, 'portals/thermal-receipt.html', {
            'invoice': invoice,
            'receipt': receipt or {'receipt_number': f'REC-{invoice.invoice_number}', 'issued_at': invoice.created_at, 'amount': invoice.amount_paid, 'invoice': invoice},
            'payment': payment,
            'copy_number': 1,
        })
    return render(request, 'portals/receipt.html', {'invoice': invoice})


@login_required
@role_required({'admin', 'manager', 'receptionist', 'guest'})
def portal_payment_receipt(request, receipt_id):
    receipt = Receipt.objects.select_related(
        'invoice__guest', 'payment_record__processed_by',
        'payment_record__cashier_shift__terminal',
    ).filter(pk=receipt_id).first()
    if not receipt:
        return HttpResponse(status=404)
    if request.user.role == 'guest' and receipt.invoice.guest_id != request.user.id:
        return HttpResponse(status=403)
    payment = getattr(receipt, 'payment_record', None)
    latest_print_job = receipt.print_jobs.select_related('terminal').first()
    terminal = (
        payment.cashier_shift.terminal if payment and payment.cashier_shift_id
        else latest_print_job.terminal if latest_print_job else None
    )
    if request.method == 'POST':
        action = request.POST.get('action', 'print')
        if action == 'print' and request.user.role in STAFF_ROLES and terminal:
            request_receipt_print(receipt=receipt, terminal=terminal, actor=request.user)
            messages.success(request, 'Receipt print job queued.')
        elif action == 'email' and receipt.invoice.guest and receipt.invoice.guest.email:
            from django.core.mail import send_mail
            import datetime
            send_mail(
                subject=f'Receipt {receipt.receipt_number} from GRACEDAY INN',
                message=(f'Hello {receipt.invoice.guest.get_full_name() or receipt.invoice.guest.username},\n\n'
                         f'Thank you for your payment.\n'
                         f'Amount Paid: NGN {receipt.amount}\n'
                         f'Receipt Number: {receipt.receipt_number}\n'
                         f'Date: {datetime.date.today().strftime("%Y-%m-%d")}\n\n'
                         f'Thank you for staying with us.'),
                from_email='noreply@gracedayinn.com',
                recipient_list=[receipt.invoice.guest.email],
                fail_silently=True,
            )
            messages.success(request, f'Receipt emailed to {receipt.invoice.guest.email}')
        return redirect('frontend:portal-payment-receipt', receipt_id=receipt.id)
    
    fmt = request.GET.get('format', 'pos').lower()
    if fmt == 'a4':
        return render(request, 'portals/receipt.html', {'invoice': receipt.invoice, 'receipt': receipt})

    copy_number = receipt.print_jobs.count() + 1 if receipt.print_jobs.exists() else 1
    return render(request, 'portals/thermal-receipt.html', {
        'receipt': receipt, 'payment': payment, 'terminal': terminal,
        'copy_number': copy_number,
    })


@login_required
@role_required(STAFF_ROLES)
def portal_cashier(request):
    if not CashierTerminal.objects.filter(is_active=True).exists():
        CashierTerminal.objects.create(code='front-desk-1', name='Front Desk 1', location='Reception')
    open_shift = get_open_shift(request.user)
    if request.method == 'POST':
        action = request.POST.get('action')
        try:
            if action == 'open':
                terminal = get_object_or_404(
                    CashierTerminal, pk=request.POST.get('terminal'), is_active=True
                )
                open_cashier_shift(
                    terminal=terminal, cashier=request.user,
                    opening_float=request.POST.get('opening_float') or 0,
                )
                messages.success(request, 'Cashier shift opened.')
            elif action == 'close' and open_shift:
                close_cashier_shift(
                    shift=open_shift, counted_cash=request.POST.get('counted_cash'),
                    actor=request.user, note=request.POST.get('note', ''),
                )
                messages.success(request, 'Cashier shift closed and reconciled.')
        except (ValidationError, TypeError) as exc:
            messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
        return redirect('frontend:portal-cashier')
    return render(request, 'portals/cashier.html', {
        'open_shift': open_shift,
        'terminals': CashierTerminal.objects.filter(is_active=True),
        'recent_shifts': CashierShift.objects.select_related('terminal', 'cashier').filter(
            cashier=request.user
        )[:20],
    })


@login_required
@role_required({'admin', 'manager', 'receptionist', 'guest'})
def portal_payments(request):
    can_manage = request.user.role in STAFF_ROLES
    payment_form = None
    if can_manage:
        initial_data = {}
        if request.method != 'POST' and request.GET.get('invoice_id'):
            inv_id = request.GET.get('invoice_id')
            inv = Invoice.objects.filter(pk=inv_id).first()
            if inv:
                initial_data['invoice'] = inv.id
                initial_data['amount'] = inv.balance
        payment_form = PaymentRecordForm(request.POST or None, initial=initial_data, user=request.user)
        if request.method == 'POST' and payment_form.is_valid():
            try:
                payment, receipt, created = record_payment(
                    invoice=payment_form.cleaned_data['invoice'],
                    amount=payment_form.cleaned_data['amount'],
                    method=payment_form.cleaned_data['method'],
                    transaction_id=payment_form.cleaned_data['transaction_id'],
                    notes=payment_form.cleaned_data['notes'],
                    actor=request.user,
                    idempotency_key=payment_form.cleaned_data['idempotency_key'],
                )
            except ValidationError as exc:
                payment_form.add_error(None, '; '.join(exc.messages))
            else:
                _notify_user(
                    recipient=payment.invoice.guest,
                    title='Payment received',
                    message=(
                        f'Payment {payment.reference} of N{payment.amount} was recorded '
                        f'for invoice {payment.invoice.invoice_number}.'
                    ),
                    notification_type='payment',
                    link=PAYMENTS_LINK,
                )
                _log_audit(
                    request,
                    event_type='payment',
                    action='record_payment',
                    target_model='Payment',
                    target_id=payment.id,
                    details={
                        'reference': payment.reference,
                        'invoice_number': payment.invoice.invoice_number,
                        'status': payment.status,
                        'amount': str(payment.amount),
                        'idempotent_replay': not created,
                    },
                )
                messages.success(request, f'Payment {payment.reference} recorded successfully.')
                return redirect(PORTAL_PAYMENTS_ROUTE)

    payments = Payment.objects.select_related('invoice', 'receipt', 'processed_by').order_by('-created_at')
    if request.user.role == 'guest':
        payments = payments.filter(invoice__guest=request.user)
    return render(
        request,
        'portals/payments.html',
        {
            'payments': payments,
            'stats': _portal_stats(request.user),
            'payment_form': payment_form,
            'can_manage_payments': can_manage,
        },
    )


@login_required
@role_required({'admin', 'manager', 'receptionist', 'guest'})
def portal_services(request):
    can_manage = request.user.role in STAFF_ROLES or request.user.role == 'guest'
    service_form = ServiceOrderCreateForm(request.POST or None, user=request.user)
    if request.method == 'POST' and service_form.is_valid():
        order = service_form.save(created_by=request.user)
        _notify_user(
            recipient=order.guest,
            title='Service order created',
            message=f'Service order {order.order_number} has been created with total N{order.total}.',
            notification_type='service',
            link=SERVICES_LINK,
        )
        _notify_staff(
            title='New service order',
            message=f'Order {order.order_number} is pending processing.',
            notification_type='service',
            link=SERVICES_LINK,
        )
        _log_audit(
            request,
            event_type='service',
            action='create_service_order',
            target_model='ServiceOrder',
            target_id=order.id,
            details={'order_number': order.order_number, 'guest_id': order.guest_id, 'total': str(order.total)},
        )
        messages.success(request, f'Service order {order.order_number} created successfully.')
        return redirect(PORTAL_SERVICES_ROUTE)

    orders = ServiceOrder.objects.select_related('guest', 'room').order_by('-created_at')
    if request.user.role == 'guest':
        orders = orders.filter(guest=request.user)
    menu_items = MenuItem.objects.select_related('category').filter(is_available=True)[:8]
    return render(
        request,
        'portals/services.html',
        {
            'orders': orders,
            'menu_items': menu_items,
            'stats': _portal_stats(request.user),
            'service_form': service_form,
            'can_manage_services': can_manage,
        },
    )


@login_required
@role_required({'admin', 'manager', 'receptionist', 'housekeeping'})
def portal_housekeeping(request):
    can_manage = request.user.role in {'admin', 'manager', 'housekeeping', 'receptionist'}
    task_form = HousekeepingTaskCreateForm(request.POST or None)
    if can_manage and request.method == 'POST' and task_form.is_valid():
        task = create_housekeeping_task(actor=request.user, **task_form.cleaned_data)
        _notify_staff(
            title='New housekeeping task',
            message=f'{task.get_task_type_display()} created for Room {task.room.number}.',
            notification_type='housekeeping',
            link=HOUSEKEEPING_LINK,
        )
        _log_audit(
            request,
            event_type='housekeeping',
            action='create_housekeeping_task',
            target_model='HousekeepingTask',
            target_id=task.id,
            details={'room': task.room.number, 'task_type': task.task_type, 'priority': task.priority},
        )
        messages.success(request, f'Housekeeping task for Room {task.room.number} created.')
        return redirect(PORTAL_HOUSEKEEPING_ROUTE)

    tasks = HousekeepingTask.objects.select_related('room', 'assigned_to').order_by('-created_at')
    return render(
        request,
        'portals/housekeeping.html',
        {
            'tasks': tasks,
            'stats': _portal_stats(request.user),
            'task_form': task_form,
            'can_manage_housekeeping': can_manage,
        },
    )


@login_required
@action_role_required(
    {
        'confirm': {'admin', 'manager', 'receptionist'},
        'start': {'admin', 'manager', 'receptionist'},
        'complete': {'admin', 'manager', 'receptionist'},
        'cancel': {'admin', 'manager', 'receptionist'},
    },
    redirect_route=PORTAL_SERVICES_ROUTE,
)
def portal_service_action(request, pk, action):
    if request.method != 'POST':
        return redirect(PORTAL_SERVICES_ROUTE)

    order = get_object_or_404(ServiceOrder, pk=pk)

    try:
        order = transition_service_order(order_id=order.pk, action=action, actor=request.user)
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
        return redirect(PORTAL_SERVICES_ROUTE)
    _log_audit(
        request,
        event_type='service',
        action=f'service_order_{action}',
        target_model='ServiceOrder',
        target_id=order.id,
        details={'order_number': order.order_number, 'new_status': order.status},
    )
    messages.success(request, f'Service order {order.order_number} set to {order.get_status_display()}.')
    return redirect(PORTAL_SERVICES_ROUTE)


@login_required
@action_role_required(
    {
        'start': {'admin', 'manager', 'housekeeping', 'receptionist'},
        'complete': {'admin', 'manager', 'housekeeping', 'receptionist'},
        'verify': {'admin', 'manager', 'receptionist'},
        'reopen': {'admin', 'manager', 'receptionist'},
    },
    redirect_route=PORTAL_HOUSEKEEPING_ROUTE,
)
def portal_housekeeping_action(request, pk, action):
    if request.method != 'POST':
        return redirect(PORTAL_HOUSEKEEPING_ROUTE)

    task = get_object_or_404(HousekeepingTask, pk=pk)
    try:
        task = transition_housekeeping_task(
            task_id=task.pk, action=action, actor=request.user,
            notes=request.POST.get('notes', ''),
        )
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
        return redirect(PORTAL_HOUSEKEEPING_ROUTE)

    _notify_staff(
        title='Housekeeping task updated',
        message=f'Task for Room {task.room.number} is now {task.get_status_display()}.',
        notification_type='housekeeping',
        link=HOUSEKEEPING_LINK,
    )
    _log_audit(
        request,
        event_type='housekeeping',
        action=f'housekeeping_{action}',
        target_model='HousekeepingTask',
        target_id=task.id,
        details={'room': task.room.number, 'new_status': task.status},
    )
    messages.success(request, f'Housekeeping task updated to {task.get_status_display()}.')
    return redirect(PORTAL_HOUSEKEEPING_ROUTE)


@login_required
@role_required({'admin', 'manager', 'receptionist', 'housekeeping'})
def portal_maintenance(request):
    form = MaintenanceTicketCreateForm(request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        ticket = create_maintenance_ticket(actor=request.user, **form.cleaned_data)
        _log_audit(
            request, event_type='housekeeping', action='maintenance_report',
            target_model='MaintenanceTicket', target_id=ticket.id,
            details={'room': ticket.room.number, 'priority': ticket.priority},
        )
        messages.success(request, f'Maintenance ticket {ticket.reference} reported.')
        return redirect('frontend:portal-maintenance')
    tickets = MaintenanceTicket.objects.select_related('room', 'assigned_to', 'reported_by')
    if request.user.role == 'housekeeping':
        tickets = tickets.filter(Q(assigned_to=request.user) | Q(reported_by=request.user))
    return render(request, 'portals/maintenance.html', {'tickets': tickets, 'ticket_form': form})


@login_required
@action_role_required({
    'start': {'admin', 'manager', 'receptionist', 'housekeeping'},
    'resolve': {'admin', 'manager', 'receptionist', 'housekeeping'},
    'approve': {'admin', 'manager'}, 'cancel': {'admin', 'manager'},
    'reopen': {'admin', 'manager'},
}, redirect_route='frontend:portal-maintenance')
def portal_maintenance_action(request, pk, action):
    if request.method != 'POST':
        return redirect('frontend:portal-maintenance')
    ticket = get_object_or_404(MaintenanceTicket, pk=pk)
    if request.user.role == 'housekeeping' and request.user not in {ticket.assigned_to, ticket.reported_by}:
        messages.error(request, 'This maintenance ticket is outside your assignment.')
        return redirect('frontend:portal-maintenance')
    try:
        ticket = transition_maintenance_ticket(
            ticket_id=ticket.pk, action=action, actor=request.user,
            notes=request.POST.get('notes', ''), actual_cost=request.POST.get('actual_cost') or None,
        )
    except ValidationError as exc:
        messages.error(request, '; '.join(exc.messages))
        return redirect('frontend:portal-maintenance')
    _log_audit(
        request, event_type='housekeeping', action=f'maintenance_{action}',
        target_model='MaintenanceTicket', target_id=ticket.id,
        details={'room': ticket.room.number, 'status': ticket.status},
    )
    messages.success(request, f'Maintenance ticket is now {ticket.get_status_display()}.')
    return redirect('frontend:portal-maintenance')


@login_required
@role_required({'admin', 'manager', 'receptionist', 'housekeeping'})
def portal_operations(request):
    form_type = request.POST.get('form_type') if request.method == 'POST' else None
    incident_form = IncidentReportCreateForm(request.POST if form_type == 'incident' else None)
    lost_form = LostFoundItemCreateForm(request.POST if form_type == 'lost_found' else None)
    if request.method == 'POST' and form_type == 'incident' and incident_form.is_valid():
        incident = create_incident(actor=request.user, **incident_form.cleaned_data)
        _log_audit(
            request, event_type='system', action='incident_report',
            target_model='IncidentReport', target_id=incident.id,
            details={'severity': incident.severity, 'incident_type': incident.incident_type},
        )
        messages.success(request, f'Incident {incident.reference} recorded.')
        return redirect('frontend:portal-operations')
    if request.method == 'POST' and form_type == 'lost_found' and lost_form.is_valid():
        item = register_lost_found_item(actor=request.user, **lost_form.cleaned_data)
        _log_audit(
            request, event_type='system', action='lost_found_register',
            target_model='LostFoundItem', target_id=item.id,
            details={'item_name': item.item_name, 'found_location': item.found_location},
        )
        messages.success(request, f'Lost-and-found item {item.reference} recorded.')
        return redirect('frontend:portal-operations')
    incidents = IncidentReport.objects.select_related('room', 'reservation', 'reported_by', 'assigned_to')
    if request.user.role == 'housekeeping':
        incidents = incidents.filter(Q(reported_by=request.user) | Q(assigned_to=request.user))
    items = LostFoundItem.objects.select_related('room', 'found_by', 'completed_by')
    return render(request, 'portals/operations.html', {
        'incident_form': incident_form, 'lost_form': lost_form,
        'incidents': incidents, 'lost_found_items': items,
    })


@login_required
@action_role_required({
    'investigate': {'admin', 'manager', 'receptionist'},
    'resolve': {'admin', 'manager'}, 'close': {'admin', 'manager'},
    'reopen': {'admin', 'manager'},
}, redirect_route='frontend:portal-operations')
def portal_incident_action(request, pk, action):
    if request.method != 'POST':
        return redirect('frontend:portal-operations')
    try:
        incident = transition_incident(
            incident_id=pk, action=action, actor=request.user,
            notes=request.POST.get('notes', ''),
        )
    except (IncidentReport.DoesNotExist, ValidationError) as exc:
        messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
    else:
        _log_audit(
            request, event_type='system', action=f'incident_{action}',
            target_model='IncidentReport', target_id=incident.id,
            details={'status': incident.status},
        )
        messages.success(request, f'Incident is now {incident.get_status_display()}.')
    return redirect('frontend:portal-operations')


@login_required
@action_role_required({
    'store': {'admin', 'manager', 'receptionist', 'housekeeping'},
    'claim': {'admin', 'manager', 'receptionist'},
    'return': {'admin', 'manager', 'receptionist'},
    'dispose': {'admin', 'manager'}, 'reopen': {'admin', 'manager', 'receptionist'},
}, redirect_route='frontend:portal-operations')
def portal_lost_found_action(request, pk, action):
    if request.method != 'POST':
        return redirect('frontend:portal-operations')
    try:
        item = transition_lost_found_item(
            item_id=pk, action=action, actor=request.user,
            notes=request.POST.get('notes', ''),
            storage_location=request.POST.get('storage_location', ''),
            claimant_name=request.POST.get('claimant_name', ''),
            claimant_contact=request.POST.get('claimant_contact', ''),
            claim_verification=request.POST.get('claim_verification', ''),
        )
    except (LostFoundItem.DoesNotExist, ValidationError) as exc:
        messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
    else:
        _log_audit(
            request, event_type='system', action=f'lost_found_{action}',
            target_model='LostFoundItem', target_id=item.id,
            details={'status': item.status},
        )
        messages.success(request, f'Item is now {item.get_status_display()}.')
    return redirect('frontend:portal-operations')


@login_required
@role_required({'admin', 'manager', 'receptionist', 'housekeeping'})
def portal_stock(request):
    form = StockMovementForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        try:
            if data['movement_type'] == 'transfer':
                movements = transfer_stock(
                    item=data['item'], source=data['location'], destination=data['destination'],
                    quantity=data['quantity'], reason=data['reason'], actor=request.user,
                    idempotency_key=data['idempotency_key'],
                )
                target = movements[0]
            else:
                target = record_stock_movement(
                    item=data['item'], location=data['location'],
                    movement_type=data['movement_type'], quantity=data['quantity'],
                    reason=data['reason'], actor=request.user,
                    idempotency_key=data['idempotency_key'],
                )
        except ValidationError as exc:
            form.add_error(None, '; '.join(exc.messages))
        else:
            _log_audit(
                request, event_type='system', action='stock_movement',
                target_model='StockMovement', target_id=target.id,
                details={'item': target.item.sku, 'movement_type': data['movement_type']},
            )
            messages.success(request, 'Stock movement posted.')
            return redirect('frontend:portal-stock')
    balances = StockBalance.objects.select_related('item', 'location')
    movements = StockMovement.objects.select_related('item', 'location', 'actor')
    if request.user.role == 'housekeeping':
        balances = balances.filter(item__category__in=['linen', 'housekeeping'])
        movements = movements.filter(item__category__in=['linen', 'housekeeping'])
    elif request.user.role == 'receptionist':
        balances = balances.filter(item__category__in=['minibar', 'other'])
        movements = movements.filter(item__category__in=['minibar', 'other'])
    return render(request, 'portals/stock.html', {
        'movement_form': form, 'balances': balances, 'movements': movements[:100],
    })


@login_required
@role_required({'admin', 'manager', 'receptionist', 'accountant'})
def portal_reports(request):
    selected_days = _selected_window_days(request)
    report, trend = _build_report_data(days=selected_days)
    
    from apps.frontend.models import AuditLog
    from apps.payments.models import CashierShift, Payment
    from django.db.models import Sum
    
    recent_audits = AuditLog.objects.select_related('actor').order_by('-sequence')[:30]
    cashier_shifts = CashierShift.objects.select_related('cashier', 'terminal').order_by('-opened_at')[:15]
    
    settlements = report['tender']

    return render(
        request,
        'portals/reports.html',
        {
            'report': report,
            'stats': _portal_stats(request.user),
            'selected_days': selected_days,
            'window_choices': sorted(ALLOWED_REPORT_WINDOWS),
            'trend_labels_json': json.dumps(trend['labels']),
            'occupancy_trend_json': json.dumps(trend['occupancy_trend']),
            'revenue_trend_json': json.dumps(trend['revenue_trend']),
            'service_sla_trend_json': json.dumps(trend['service_sla_trend']),
            'recent_audits': recent_audits,
            'cashier_shifts': cashier_shifts,
            'settlements': settlements,
        },
    )


@login_required
@role_required({'admin', 'manager', 'receptionist', 'accountant'})
def portal_reports_export_csv(request):
    selected_days = _selected_window_days(request)
    report, trend = _build_report_data(days=selected_days)
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="graceday-inn-report-{selected_days}d.csv"'
    writer = csv.writer(response)

    writer.writerow(['GRACEDAY INN Performance Report'])
    writer.writerow(['Generated At', timezone.localtime().strftime('%Y-%m-%d %H:%M')])
    writer.writerow(['Window (Days)', selected_days])
    writer.writerow([])
    writer.writerow(['Metric', 'Value'])
    writer.writerow(['Total Revenue', report['total_revenue']])
    writer.writerow(['Gross Revenue', report['gross_revenue']])
    writer.writerow(['Payments Collected', report['payments_collected']])
    writer.writerow(['Refunds', report['refunds']])
    writer.writerow(['Open Balance', report['open_balance']])
    writer.writerow(['Cash Variance', report['cash_variance']])
    writer.writerow(['Open Cashier Shifts', report['open_shifts']])
    writer.writerow(['Total Reservations', report['total_reservations']])
    writer.writerow(['Confirmed Reservations', report['confirmed_reservations']])
    writer.writerow(['Occupied Rooms', report['occupied_rooms']])
    writer.writerow(['Available Rooms', report['available_rooms']])
    writer.writerow(['Pending Housekeeping', report['pending_housekeeping']])
    writer.writerow(['Service SLA (Avg Min)', report['service_sla_minutes']])
    writer.writerow(['Housekeeping Turnaround (Avg Min)', report['housekeeping_turnaround_minutes']])
    writer.writerow(['Completed Service Orders', report['completed_service_orders']])
    writer.writerow(['Completed Housekeeping Tasks', report['completed_housekeeping_tasks']])
    writer.writerow([])
    writer.writerow(['Date', 'Occupancy %', 'Revenue', 'Service SLA (Min)'])
    for index, label in enumerate(trend['labels']):
        writer.writerow(
            [
                label,
                trend['occupancy_trend'][index],
                trend['revenue_trend'][index],
                trend['service_sla_trend'][index],
            ]
        )
    return response


@login_required
@role_required({'admin', 'manager', 'receptionist', 'accountant'})
def portal_reports_export_pdf(request):
    selected_days = _selected_window_days(request)
    report, trend = _build_report_data(days=selected_days)
    return _render_report_pdf(report, trend, days=selected_days)


@login_required
@role_required({'admin', 'manager', 'accountant'})
def portal_financial_audit(request):
    if request.method == 'POST':
        action = request.POST.get('action', 'prepare')
        if action == 'prepare':
            start = parse_date(request.POST.get('period_start', ''))
            end = parse_date(request.POST.get('period_end', ''))
            try:
                prepare_financial_audit(
                    period_start=start, period_end=end, run_type=request.POST.get('run_type', 'daily'),
                    actor=request.user,
                )
                messages.success(request, 'Financial audit pack prepared for independent review.')
            except (ValidationError, TypeError, ValueError) as exc:
                messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
        elif action == 'approve' and request.user.role in {'admin', 'manager'}:
            run = get_object_or_404(FinancialAuditRun, pk=request.POST.get('audit_id'))
            try:
                approve_financial_audit(audit_run=run, actor=request.user, note=request.POST.get('note', ''))
                messages.success(request, 'Financial audit approved and sealed.')
            except ValidationError as exc:
                messages.error(request, '; '.join(exc.messages))
        return redirect('frontend:portal-financial-audit')
    return render(request, 'portals/financial-audit.html', {
        'audit_runs': FinancialAuditRun.objects.select_related('prepared_by', 'approved_by')[:30],
        'today': timezone.localdate(),
        'can_approve': request.user.role in {'admin', 'manager'},
    })


def public_billboard(request):
    """High-contrast unattended reception display with rotating hotel content."""
    promotions = Promotion.objects.filter(
        is_active=True, valid_from__lte=timezone.now(), valid_to__gte=timezone.now()
    )[:8]
    rooms = Room.objects.filter(is_active=True, is_sellable=True).select_related('room_type').order_by('number')[:8]
    announcements = NewsletterMessage.objects.filter(status='sent').exclude(featured_image='').order_by('-sent_at')[:8]
    return render(request, 'publicsite/billboard.html', {
        'promotions': promotions, 'rooms': rooms, 'announcements': announcements,
        'billboard_assets': [
            {'image': 'img/hero/hero-1.jpg', 'eyebrow': 'A warm welcome', 'title': 'Arrive curious. Leave restored.', 'body': 'A calm Abuja stay with attentive service, generous spaces, and the little details that make travel easier.', 'icon': 'flaticon-026-bed'},
            {'image': 'img/dining.png', 'eyebrow': 'Taste the moment', 'title': 'Good food. Good company.', 'body': 'Enjoy memorable dining and catering from our kitchen, prepared for relaxed evenings and busy days.', 'icon': 'flaticon-033-dinner'},
            {'image': 'img/lounge 2.png', 'eyebrow': 'Slow down here', 'title': 'Comfort has a rhythm.', 'body': 'Find a quiet corner, recharge between plans, and let our team take care of the rest.', 'icon': 'flaticon-036-parking'},
            {'image': 'img/room view.png', 'eyebrow': 'Made for rest', 'title': 'Your room, your reset.', 'body': 'Thoughtful rooms, reliable Wi-Fi, air conditioning, entertainment, and room to breathe.', 'icon': 'flaticon-029-wifi'},
            {'image': 'img/Laundry room.png', 'eyebrow': 'Travel lighter', 'title': 'Freshness on your schedule.', 'body': 'Ask reception about express laundry, self-service options, and convenient collection times.', 'icon': 'flaticon-024-towel'},
            {'image': 'img/Conference  room.PNG', 'eyebrow': 'Bring people together', 'title': 'Meetings with room to think.', 'body': 'Create a polished setting for conferences, celebrations, team sessions, and private gatherings.', 'icon': 'flaticon-044-clock-1'},
        ],
    })


@login_required
def portal_profile(request):
    user = request.user

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        phone = request.POST.get('phone', '').strip()
        id_document = request.FILES.get('id_document')

        user.first_name = first_name
        user.last_name = last_name
        user.phone = phone
        
        update_fields = ['first_name', 'last_name', 'phone']
        
        if id_document:
            user.id_document = id_document
            update_fields.append('id_document')
            
        user.save(update_fields=update_fields)

        _log_audit(
            request, event_type='security', action='update_profile',
            target_model='UserProfile', target_id=user.id,
            details={'first_name': first_name, 'last_name': last_name, 'phone': phone},
        )
        messages.success(request, 'Your profile information has been updated successfully.')

        return redirect('frontend:portal-profile')

    return render(request, 'portals/profile.html', {'stats': _portal_stats(user)})


@login_required
def portal_notifications(request):
    notifications = Notification.objects.filter(recipient=request.user).order_by('-created_at')
    notifications.filter(is_read=False).update(is_read=True)
    return render(request, 'portals/notifications.html', {'notifications': notifications, 'stats': _portal_stats(request.user)})


@login_required
@role_required({'admin', 'manager', 'receptionist'})
def portal_inquiries(request):
    cases = InquiryCase.objects.select_related('owner', 'requester', 'reservation').prefetch_related('messages')
    status_filter = request.GET.get('status')
    if status_filter:
        cases = cases.filter(status=status_filter)
    return render(request, 'portals/inquiries.html', {
        'cases': cases, 'status_filter': status_filter,
        'now': timezone.now(), 'status_choices': InquiryCase.STATUS_CHOICES,
    })


@login_required
@role_required({'admin', 'manager', 'receptionist'})
def portal_inquiry_detail(request, pk):
    case = get_object_or_404(
        InquiryCase.objects.select_related('owner', 'requester').prefetch_related(
            'messages__sender', 'history', 'attachments__uploaded_by'
        ),
        pk=pk,
    )
    if request.method == 'POST':
        command = request.POST.get('command')
        try:
            if command == 'attachment':
                if not request.FILES.get('attachment'):
                    raise ValidationError('Choose a file to attach.')
                add_inquiry_attachment(
                    case=case, uploaded_file=request.FILES['attachment'], actor=request.user,
                )
            elif command == 'reply':
                add_inquiry_reply(
                    case_id=case.id, actor=request.user, body=request.POST.get('body', '').strip(),
                    internal=request.POST.get('internal') == 'on',
                )
            else:
                case = transition_inquiry(
                    case_id=case.id, action=command, actor=request.user,
                    notes=request.POST.get('notes', ''), outcome=request.POST.get('outcome', ''),
                )
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
        else:
            _log_audit(
                request, event_type='service', action=f'inquiry_{command}',
                target_model='InquiryCase', target_id=case.id,
                details={'reference': str(case.reference), 'status': case.status},
            )
            messages.success(request, 'Inquiry updated.')
        return redirect('frontend:portal-inquiry-detail', pk=case.id)
    return render(request, 'portals/inquiry-detail.html', {'case': case})


@login_required
def portal_inquiry_attachment_download(request, pk):
    from apps.notifications.models import InquiryAttachment
    attachment = get_object_or_404(InquiryAttachment.objects.select_related('case'), pk=pk)
    is_staff = request.user.is_superuser or request.user.role in {'admin', 'manager', 'receptionist'}
    if not is_staff and attachment.case.requester_id != request.user.id:
        return HttpResponse(status=403)
    return FileResponse(
        attachment.file.open('rb'), as_attachment=True, filename=attachment.original_name,
        content_type=attachment.content_type,
    )


@login_required
@role_required({'admin', 'manager'})
def portal_management(request):
    if request.method == 'POST':
        if request.POST.get('command') in {'alert_acknowledge', 'alert_resolve'}:
            try:
                transition_alert(
                    alert_id=request.POST.get('alert_id'),
                    action=request.POST['command'].removeprefix('alert_'), actor=request.user,
                    notes=request.POST.get('notes', ''),
                )
            except (ValidationError, OperationalAlert.DoesNotExist) as exc:
                messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
            else:
                messages.success(request, 'Operational alert updated.')
            return redirect('frontend:portal-management')
        if request.POST.get('command') == 'manager_pack':
            try:
                business_date = parse_date(request.POST.get('business_date', ''))
                if not business_date or business_date >= timezone.localdate():
                    raise ValidationError('Manager packs can only cover completed business dates.')
                pack, created = generate_management_pack(business_date=business_date, actor=request.user)
            except ValidationError as exc:
                messages.error(request, '; '.join(exc.messages))
            else:
                messages.success(request, f'Manager pack {pack.business_date} {"generated" if created else "already exists"}.')
            return redirect('frontend:portal-management')
        query = create_management_query(
            title=request.POST.get('title', '').strip(),
            description=request.POST.get('description', '').strip(), actor=request.user,
            priority=request.POST.get('priority', 'normal'),
            source_model=request.POST.get('source_model', '').strip(),
            source_id=request.POST.get('source_id', '').strip(),
        )
        messages.success(request, f'Management query {query.reference} raised.')
        return redirect('frontend:portal-management')
    today = timezone.localdate()
    return render(request, 'portals/management.html', {
        'live_metrics': calculate_daily_metrics(today),
        'booking_pace': calculate_booking_pace(),
        'management_exceptions': calculate_management_exceptions(),
        'snapshots': DailyMetricSnapshot.objects.all()[:30],
        'queries': ManagementQuery.objects.select_related('raised_by', 'assigned_to')[:50],
        'audits': NightAuditRun.objects.select_related('completed_by', 'snapshot')[:30],
        'manager_packs': ManagementPack.objects.select_related('generated_by')[:30],
        'scheduled_jobs': ScheduledJob.objects.all(),
        'failed_job_runs': JobExecution.objects.filter(status='failed').select_related('job')[:20],
        'contact_sync_failures': BrevoContactSync.objects.filter(status__in=['deferred', 'failed'])[:20],
        'operational_alerts': OperationalAlert.objects.filter(
            status__in=['open', 'acknowledged'],
        ).select_related('rule', 'acknowledged_by')[:50],
        'default_audit_date': today - timedelta(days=1),
    })


@login_required
@role_required({'admin', 'manager'})
def portal_management_pack_download(request, pk, file_format):
    pack = get_object_or_404(ManagementPack, pk=pk)
    if pack.expires_at <= timezone.now():
        raise Http404('This manager pack has expired.')
    field = pack.pdf_file if file_format == 'pdf' else pack.csv_file if file_format == 'csv' else None
    if not field:
        raise Http404('Unknown manager pack format.')
    return FileResponse(field.open('rb'), as_attachment=True, filename=field.name.rsplit('/', 1)[-1])


@login_required
@role_required({'admin', 'manager'})
def portal_management_query(request, pk):
    query = get_object_or_404(
        ManagementQuery.objects.select_related('raised_by', 'assigned_to').prefetch_related('notes__author', 'history'),
        pk=pk,
    )
    if request.method == 'POST':
        command = request.POST.get('command')
        try:
            if command == 'note':
                add_management_query_note(
                    query=query, actor=request.user, body=request.POST.get('body', ''),
                    evidence=request.FILES.get('evidence'),
                )
            else:
                query = transition_management_query(
                    query_id=query.id, action=command, actor=request.user,
                    resolution=request.POST.get('resolution', ''),
                )
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
        else:
            messages.success(request, 'Management query updated.')
        return redirect('frontend:portal-management-query', pk=query.id)
    return render(request, 'portals/management-query.html', {'query': query})


@login_required
@role_required({'admin', 'manager'})
def portal_night_audit(request):
    raw_date = request.POST.get('business_date') or request.GET.get('business_date')
    default_date = timezone.localdate() - timedelta(days=1)
    try:
        business_date = timezone.datetime.strptime(raw_date, '%Y-%m-%d').date() if raw_date else default_date
    except (TypeError, ValueError):
        business_date = default_date

    if request.method == 'GET':
        return render(request, 'portals/night-audit-confirm.html', {
            'business_date': business_date.strftime('%Y-%m-%d'),
            'stats': _portal_stats(request.user),
        })

    try:
        audit = run_night_audit(business_date=business_date, actor=request.user)
    except (ValidationError, ValueError) as exc:
        messages.error(request, '; '.join(getattr(exc, 'messages', [str(exc)])))
    else:
        messages.success(request, f'Night audit {audit.reference} for {business_date} completed successfully.')
    return redirect('frontend:portal-management')


@login_required
@role_required({'admin', 'manager', 'receptionist'})
def portal_chat(request):
    from django.conf import settings
    conversations = ChatConversation.objects.select_related('guest', 'assigned_to').prefetch_related('messages')
    status_filter = request.GET.get('status')
    if status_filter:
        conversations = conversations.filter(status=status_filter)
    return render(request, 'portals/chat.html', {
        'conversations': conversations, 'status_filter': status_filter,
        'status_choices': ChatConversation.STATUS_CHOICES,
        'tawkto_active': bool(getattr(settings, 'TAWKTO_EMBED_URL', '')),
    })


@login_required
@role_required({'admin', 'manager', 'receptionist'})
def portal_chat_detail(request, reference):
    conversation = get_object_or_404(
        ChatConversation.objects.select_related('guest', 'assigned_to').prefetch_related('messages__sender'),
        reference=reference,
    )
    if request.method == 'POST':
        command = request.POST.get('command')
        try:
            if command in {'reply', 'note'}:
                body = request.POST.get('body', '')
                canned_reply_id = request.POST.get('canned_reply_id')
                if command == 'reply' and canned_reply_id:
                    canned_reply = ChatCannedReply.objects.filter(
                        pk=canned_reply_id, status='approved',
                    ).first()
                    if not canned_reply:
                        raise ValidationError('That canned reply is unavailable or not approved.')
                    body = canned_reply.body
                send_chat_message(
                    conversation=conversation, actor=request.user,
                    body=body, internal=command == 'note',
                )
                if command == 'reply' and canned_reply_id:
                    ChatCannedReply.objects.filter(pk=canned_reply.id).update(use_count=F('use_count') + 1)
            else:
                conversation = transition_chat(
                    conversation_id=conversation.id, action=command, actor=request.user,
                    disposition=request.POST.get('disposition', ''),
                )
        except ValidationError as exc:
            messages.error(request, '; '.join(exc.messages))
        else:
            messages.success(request, 'Conversation updated.')
        return redirect('frontend:portal-chat-detail', reference=conversation.reference)
    return render(request, 'portals/chat-detail.html', {
        'conversation': conversation,
        'canned_replies': ChatCannedReply.objects.filter(status='approved'),
    })


@login_required
def portal_settings(request):
    can_manage = request.user.is_superuser or request.user.role == 'admin'
    if request.method == 'POST' and can_manage:
        flag_id = request.POST.get('flag_id')
        if flag_id:
            flag = FeatureFlag.objects.filter(pk=flag_id).first()
            if flag:
                flag.is_enabled = request.POST.get('is_enabled') == 'on'
                flag.save()
                _log_audit(
                    request, event_type='security', action='toggle_feature_flag',
                    target_model='FeatureFlag', target_id=flag.id,
                    details={'key': flag.key, 'is_enabled': flag.is_enabled},
                )
                messages.success(request, f'Feature flag "{flag.key}" updated.')
                return redirect('frontend:portal-settings')

    flags = FeatureFlag.objects.all().order_by('key')
    settings_qs = OperationalSetting.objects.filter(is_secret=False).order_by('key') if (request.user.is_superuser or request.user.role in {'admin', 'manager'}) else []
    return render(request, 'portals/settings.html', {
        'feature_flags': flags,
        'operational_settings': settings_qs,
        'can_manage_settings': can_manage,
        'stats': _portal_stats(request.user),
    })


def send_html_email(subject, template_name, context, recipient_list):
    html_content = render_to_string(template_name, context)
    text_content = strip_tags(html_content)
    try:
        results = [
            enqueue_email(
                purpose=template_name.rsplit('/', 1)[-1].removesuffix('.html'),
                recipient_email=recipient,
                subject=subject,
                html_body=html_content,
                text_body=text_content,
                send_now=True,
            )[0]
            for recipient in recipient_list
        ]
        return bool(results) and all(message.status in {'accepted', 'queued'} for message in results)
    except Exception:
        logger.exception('Email delivery failed for template %s', template_name)
        return False


def portal_verify_booking(request):
    if 'booking_request_data' not in request.session or 'booking_verify_hash' not in request.session:
        messages.error(request, 'No active booking verification found. Please initiate a booking first.')
        return redirect('frontend:public-home')
    
    booking_data = request.session['booking_request_data']
    if request.method == 'POST':
        entered_code = request.POST.get('verification_code', '').strip()
        verification_result = check_booking_verification(request, entered_code)
        if verification_result == 'verified':
            email = booking_data['email'].lower().strip()
            first_name = booking_data['first_name'].strip()
            last_name = booking_data['last_name'].strip()
            phone = booking_data['phone'].strip()
            
            with transaction.atomic():
                from apps.accounts.models import normalize_guest_email
                user = UserProfile.objects.filter(
                    normalized_email=normalize_guest_email(email), merged_into__isnull=True,
                ).first()
                setup_url = None
                
                if not user:
                    base_username = email.split('@')[0] or 'guest'
                    username = base_username
                    index = 1
                    while UserProfile.objects.filter(username=username).exists():
                        username = f'{base_username}{index}'
                        index += 1
                        
                    user = UserProfile.objects.create(
                        username=username,
                        email=email,
                        first_name=first_name,
                        last_name=last_name,
                        phone=phone,
                        role='guest',
                        is_active=True,
                    )
                    user.set_unusable_password()
                    user.save()
                    
                    GuestProfile.objects.get_or_create(user=user)
                else:
                    updated = False
                    if not user.first_name:
                        user.first_name = first_name
                        updated = True
                    if not user.last_name:
                        user.last_name = last_name
                        updated = True
                    if phone and not user.phone:
                        user.phone = phone
                        updated = True
                    if updated:
                        user.save(update_fields=['first_name', 'last_name', 'phone'])
                    
                    GuestProfile.objects.get_or_create(user=user)
                
                try:
                    reservation = convert_quote(
                        quote_id=booking_data['quote_id'],
                        guest=user,
                        created_by=user,
                        source='direct_website',
                        notes=f"Requested via website with email verification. Contact: {phone or 'N/A'}",
                    )
                except ValidationError as exc:
                    clear_booking_verification(request)
                    messages.error(request, '; '.join(exc.messages))
                    return redirect('frontend:public-home')
                
                _notify_staff(
                    title='New booking request',
                    message=(
                        f'Booking {reservation.reservation_number} created for Room {reservation.room.number} '
                        f'({reservation.check_in_date} to {reservation.check_out_date}).'
                    ),
                    notification_type='reservation',
                    link=RESERVATIONS_LINK,
                )
                
                login_url = request.build_absolute_uri(reverse('frontend:portal-sign-in'))
                if not user.has_usable_password():
                    uid = urlsafe_base64_encode(force_bytes(user.pk))
                    token = default_token_generator.make_token(user)
                    setup_url = request.build_absolute_uri(
                        reverse('frontend:portal-set-password', args=[uid, token])
                    )
                send_html_email(
                    subject='GraceDay Inn - Booking Confirmed',
                    template_name='emails/booking_confirmed.html',
                    context={
                        'first_name': first_name,
                        'reservation_number': reservation.reservation_number,
                        'username': user.username,
                        'setup_url': setup_url,
                        'login_url': login_url,
                    },
                    recipient_list=[email],
                )
                
                if not setup_url:
                    login(request, user)
                
                clear_booking_verification(request)
                
                if setup_url:
                    messages.success(request, f'Booking request {reservation.reservation_number} created. Check your email to set your portal password.')
                else:
                    messages.success(request, f'Booking request {reservation.reservation_number} created! Welcome back.')
                    
                return redirect(PORTAL_DASHBOARD_ROUTE)
        elif verification_result == 'invalid':
            messages.error(request, 'Invalid verification code. Please try again.')
        elif verification_result == 'expired':
            if booking_data.get('quote_id'):
                release_quote(quote_id=booking_data['quote_id'])
            messages.error(request, 'The verification code has expired. Please start the booking again.')
            return redirect('frontend:public-home')
        else:
            if booking_data.get('quote_id'):
                release_quote(quote_id=booking_data['quote_id'])
            messages.error(request, 'Verification is no longer available. Please start the booking again.')
            return redirect('frontend:public-home')
            
    return render(request, 'portals/verify-booking.html', {'email': booking_data['email']})


def subscribe_newsletter(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        if email:
            subscription, created = NewsletterSubscription.objects.get_or_create(email=email)
            if created or not subscription.is_active:
                subscription.is_active = True
                subscription.save()
                ContactPreference.objects.update_or_create(
                    email=email, purpose='marketing', defaults={
                        'consent_granted': True, 'consent_source': 'website_form',
                        'consent_version': '2026-08', 'granted_at': timezone.now(),
                        'withdrawn_at': None,
                    },
                )
                Suppression.objects.filter(email__iexact=email, reason__in=['manual', 'unsubscribe']).delete()
                
                send_html_email(
                    subject='Welcome to GraceDay Inn Newsletter',
                    template_name='emails/newsletter_welcome.html',
                    context={},
                    recipient_list=[email],
                )
                messages.success(request, 'Thank you for subscribing to our newsletter!')
            else:
                messages.info(request, 'You are already subscribed to our newsletter.')
        else:
            messages.error(request, 'Please enter a valid email address.')
            
    next_url = request.META.get('HTTP_REFERER') or reverse('frontend:public-home')
    return redirect(next_url)
