import csv
import json
import random
import string
from datetime import timedelta

from django.core.mail import send_mail, EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags

from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import GuestProfile, UserProfile
from apps.billing.models import Invoice, InvoiceItem, Receipt
from apps.housekeeping.models import HousekeepingTask
from apps.notifications.models import Notification
from apps.payments.models import Payment
from apps.reservations.models import Reservation
from apps.rooms.models import Amenity, Room, RoomType
from apps.services.models import MenuItem, ServiceCategory, ServiceOrder

from .decorators import action_role_required, role_required
from .forms import (
    BookingRequestForm,
    ContactForm,
    HousekeepingTaskCreateForm,
    PaymentRecordForm,
    ServiceOrderCreateForm,
    PortalReservationForm,
    PortalLoginForm,
    PortalSignUpForm,
)
from .models import AuditLog, NewsletterSubscription

FRONTEND_ROUTE_PREFIX = 'frontend:'
PORTAL_DASHBOARD_ROUTE = f'{FRONTEND_ROUTE_PREFIX}portal-dashboard'
PORTAL_RESERVATIONS_ROUTE = f'{FRONTEND_ROUTE_PREFIX}portal-reservations'
PORTAL_PAYMENTS_ROUTE = f'{FRONTEND_ROUTE_PREFIX}portal-payments'
PORTAL_SERVICES_ROUTE = f'{FRONTEND_ROUTE_PREFIX}portal-services'
PORTAL_HOUSEKEEPING_ROUTE = f'{FRONTEND_ROUTE_PREFIX}portal-housekeeping'
STAFF_ROLES = {'admin', 'manager', 'receptionist'}
RESERVATIONS_LINK = '/portal/reservations/'
PAYMENTS_LINK = '/portal/payments/'
SERVICES_LINK = '/portal/services/'
HOUSEKEEPING_LINK = '/portal/housekeeping/'
PORTAL_BILLING_LINK = '/portal/billing/'
ALLOWED_REPORT_WINDOWS = {7, 14, 30, 90}


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


def _build_trend_series(days=14):
    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    labels = [start + timedelta(days=index) for index in range(days)]

    active_reservation_statuses = {'confirmed', 'checked_in', 'checked_out'}
    total_rooms = max(Room.objects.filter(is_active=True).count(), 1)
    occupancy_trend = []
    for day in labels:
        occupied_count = Reservation.objects.filter(
            status__in=active_reservation_statuses,
            check_in_date__lte=day,
            check_out_date__gt=day,
        ).count()
        occupancy_trend.append(round((occupied_count / total_rooms) * 100, 2))

    revenue_map = {
        row['day']: float(row['total'] or 0)
        for row in Payment.objects.filter(
            status='completed',
            created_at__date__range=(start, today),
        )
        .annotate(day=TruncDate('created_at'))
        .values('day')
        .annotate(total=Sum('amount'))
    }
    revenue_trend = [round(revenue_map.get(day, 0.0), 2) for day in labels]

    service_sla_map = {
        row['day']: _duration_to_minutes(row['avg_duration'])
        for row in ServiceOrder.objects.filter(
            status='completed',
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
        'total_revenue': Invoice.objects.aggregate(total=Sum('amount_paid'))['total'] or 0,
        'open_balance': Invoice.objects.aggregate(total=Sum('balance'))['total'] or 0,
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


def _validate_reservation_transition(reservation, action, action_map):
    if action not in action_map:
        return False, 'Unknown action.'

    allowed_from, next_status = action_map[action]
    if allowed_from and reservation.status != allowed_from:
        return False, f'Reservation cannot move from {reservation.status} to {next_status}.'

    if action == 'confirm':
        overlap_exists = Reservation.objects.filter(
            room=reservation.room,
            status__in=['confirmed', 'checked_in'],
            check_in_date__lt=reservation.check_out_date,
            check_out_date__gt=reservation.check_in_date,
        ).exclude(pk=reservation.pk).exists()
        if overlap_exists:
            return False, 'Cannot confirm reservation. The room has a conflicting active booking.'

    return True, ''


def _apply_reservation_side_effects(reservation, action):
    if action == 'check_in':
        reservation.actual_check_in = timezone.now()
        reservation.room.status = 'occupied'
        reservation.room.save(update_fields=['status'])
    elif action == 'check_out':
        reservation.actual_check_out = timezone.now()
        reservation.room.status = 'housekeeping'
        reservation.room.save(update_fields=['status'])
        HousekeepingTask.objects.get_or_create(
            room=reservation.room,
            status='pending',
            task_type='cleaning',
            defaults={
                'priority': 'high',
                'notes': f'Auto-created at checkout for reservation {reservation.reservation_number}.',
                'created_by': reservation.created_by,
            },
        )


def _send_reservation_action_notification(reservation, action):
    if action == 'confirm':
        invoice = _ensure_invoice_for_reservation(reservation)
        _notify_user(
            recipient=reservation.guest,
            title='Reservation confirmed',
            message=(
                f'Your reservation {reservation.reservation_number} is confirmed. '
                f'Invoice {invoice.invoice_number} has been generated.'
            ),
            notification_type='reservation',
            link=PORTAL_BILLING_LINK,
        )
        return

    action_messages = {
        'check_in': ('Checked in', 'You have been checked in for reservation '),
        'check_out': ('Checked out', 'You have been checked out for reservation '),
        'cancel': ('Reservation cancelled', 'Reservation '),
    }
    title, prefix = action_messages[action]
    suffix = ' has been cancelled.' if action == 'cancel' else '.'
    _notify_user(
        recipient=reservation.guest,
        title=title,
        message=f'{prefix}{reservation.reservation_number}{suffix}',
        notification_type='reservation',
        link=RESERVATIONS_LINK,
    )


def _portal_stats(user):
    room_counts = Room.objects.values('status').annotate(total=Count('id'))
    room_status = {item['status']: item['total'] for item in room_counts}
    today = timezone.localdate()
    reservations_qs = Reservation.objects.select_related('guest', 'room', 'room__room_type')
    if user.role == 'guest':
        reservations_qs = reservations_qs.filter(guest=user)
    invoices_qs = Invoice.objects.select_related('guest', 'reservation')
    if user.role == 'guest':
        invoices_qs = invoices_qs.filter(guest=user)

    service_orders_qs = ServiceOrder.objects.all()
    if user.role == 'guest':
        service_orders_qs = service_orders_qs.filter(guest=user)
    service_sla_duration = service_orders_qs.filter(status='completed').aggregate(
        avg_duration=Avg(
            ExpressionWrapper(
                F('updated_at') - F('created_at'),
                output_field=DurationField(),
            )
        )
    )['avg_duration']

    housekeeping_qs = HousekeepingTask.objects.all()
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

    return {
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


def home(request):
    featured_rooms = RoomType.objects.prefetch_related('amenities').all()[:6]
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
    form = BookingRequestForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        if request.user.is_authenticated:
            reservation = form.create_reservation(request.user)
            _notify_staff(
                title='New booking request',
                message=(
                    f'Booking {reservation.reservation_number} created for Room {reservation.room.number} '
                    f'({reservation.check_in_date} to {reservation.check_out_date}).'
                ),
                notification_type='reservation',
                link=RESERVATIONS_LINK,
            )
            messages.success(
                request,
                f'Booking request {reservation.reservation_number} created successfully for GRACEDAY INN.',
            )
            return redirect('frontend:public-home')
        else:
            booking_data = {
                'first_name': form.cleaned_data['first_name'],
                'last_name': form.cleaned_data['last_name'],
                'email': form.cleaned_data['email'],
                'phone': form.cleaned_data['phone'],
                'check_in_date': form.cleaned_data['check_in_date'].isoformat(),
                'check_out_date': form.cleaned_data['check_out_date'].isoformat(),
                'room_id': form.cleaned_data['room'].id,
                'num_adults': form.cleaned_data['num_adults'],
                'num_children': form.cleaned_data['num_children'],
                'special_requests': form.cleaned_data['special_requests'],
            }
            code = str(random.randint(100000, 999999))
            request.session['booking_request_data'] = booking_data
            request.session['booking_verify_code'] = code
            
            send_html_email(
                subject='GRACEDAY INN - Verify your booking',
                template_name='emails/verify_email.html',
                context={'first_name': booking_data['first_name'], 'code': code},
                recipient_list=[booking_data['email']],
            )
                
            messages.info(request, 'A verification code has been sent to your email. Please enter it below to complete your booking.')
            return redirect('frontend:portal-verify-booking')

    context = {
        'booking_form': form,
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
    }

    navigation_results = []
    for label, route in navigation.items():
        if label in query_lower or query_lower in label:
            navigation_results.append({'title': label.title(), 'url': reverse(route)})

    room_results = Room.objects.filter(is_active=True).filter(
        Q(number__icontains=query)
        | Q(description__icontains=query)
        | Q(notes__icontains=query)
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
        },
    )


def public_rooms(request):
    rooms_qs = Room.objects.select_related('room_type').filter(is_active=True)
    room_type_id = request.GET.get('room_type')
    occupancy = request.GET.get('occupancy')
    max_price = request.GET.get('max_price')
    if room_type_id:
        rooms_qs = rooms_qs.filter(room_type_id=room_type_id)
    if occupancy:
        try:
            rooms_qs = rooms_qs.filter(room_type__max_occupancy__gte=int(occupancy))
        except (TypeError, ValueError):
            pass
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
        'selected_occupancy': occupancy or '',
        'selected_max_price': max_price or '',
    }
    return render(request, 'publicsite/rooms.html', context)


def room_detail(request, pk):
    room = get_object_or_404(Room.objects.select_related('room_type'), pk=pk, is_active=True)
    similar_rooms = Room.objects.select_related('room_type').filter(
        room_type=room.room_type,
        is_active=True,
    ).exclude(pk=room.pk)[:3]
    return render(request, 'publicsite/room-details.html', {'room': room, 'similar_rooms': similar_rooms})


def blog(request):
    return render(request, 'publicsite/blog.html')


def blog_detail(request):
    return render(request, 'publicsite/blog-details.html')


def public_dining(request):
    categories = ServiceCategory.objects.prefetch_related('menu_items').all()
    return render(request, 'publicsite/dining.html', {'categories': categories})

def public_laundry(request):
    return render(request, 'publicsite/laundry.html')

def public_offers(request):
    offers = []
    room_types = RoomType.objects.all()[:4]
    for room_type in room_types:
        offers.append(
            {
                'title': f'{room_type.name} Escape',
                'description': f'Stay in {room_type.name} with curated in-room amenities and priority service.',
                'price': room_type.base_price,
                'capacity': room_type.max_occupancy,
            }
        )
    return render(
        request,
        'publicsite/offers.html',
        {
            'offers': offers,
            'service_highlights': MenuItem.objects.filter(is_available=True).select_related('category')[:6],
        },
    )


def contact(request):
    form = ContactForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        messages.success(request, 'Thanks for contacting GRACEDAY INN. Our team will reach out soon.')
        return redirect('frontend:public-contact')
    return render(request, 'publicsite/contact.html', {'form': form})


def portal_sign_in(request):
    if request.user.is_authenticated:
        return redirect(PORTAL_DASHBOARD_ROUTE)
    form = PortalLoginForm(request, data=request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.get_user())
        messages.success(request, 'Welcome back to GRACEDAY INN portal.')
        return redirect(PORTAL_DASHBOARD_ROUTE)
    return render(request, 'portals/sign-in.html', {'form': form})


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


@login_required
def portal_logout(request):
    logout(request)
    messages.info(request, 'You are signed out.')
    return redirect('frontend:portal-sign-in')


@login_required
def portal_dashboard(request):
    selected_days = _selected_window_days(request)
    trend_data = _build_trend_series(days=selected_days)
    
    recent_notifications = Notification.objects.filter(recipient=request.user).order_by('-created_at')[:5]
    
    recent_reservations = Reservation.objects.select_related('guest', 'room', 'room__room_type').order_by('-created_at')
    if request.user.role == 'guest':
        recent_reservations = recent_reservations.filter(guest=request.user)
    recent_reservations = recent_reservations[:5]
    
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
def portal_rooms(request):
    rooms = Room.objects.select_related('room_type').all()
    return render(request, 'portals/tables.html', {'rooms': rooms, 'stats': _portal_stats(request.user)})


@login_required
def portal_reservations(request):
    can_manage = request.user.role in STAFF_ROLES
    reservation_form = None
    if can_manage:
        reservation_form = PortalReservationForm(request.POST or None)
        if request.method == 'POST' and reservation_form.is_valid():
            reservation = reservation_form.save(commit=False)
            reservation.created_by = request.user
            reservation.status = 'pending'
            reservation.save()
            _notify_user(
                recipient=reservation.guest,
                title='Reservation created',
                message=f'Your reservation {reservation.reservation_number} has been created and is pending confirmation.',
                notification_type='reservation',
                link=RESERVATIONS_LINK,
            )
            messages.success(request, f'Reservation {reservation.reservation_number} created successfully.')
            return redirect(PORTAL_RESERVATIONS_ROUTE)

    reservations = Reservation.objects.select_related('guest', 'room', 'room__room_type').order_by('-created_at')
    if request.user.role == 'guest':
        reservations = reservations.filter(guest=request.user)
    return render(
        request,
        'portals/reservations.html',
        {
            'reservations': reservations,
            'stats': _portal_stats(request.user),
            'reservation_form': reservation_form,
            'can_manage_reservations': can_manage,
        },
    )


@login_required
@action_role_required(
    {
        'confirm': {'admin', 'manager', 'receptionist'},
        'check_in': {'admin', 'manager', 'receptionist'},
        'check_out': {'admin', 'manager', 'receptionist'},
        'cancel': {'admin', 'manager', 'receptionist', 'guest'},
    },
    redirect_route=PORTAL_RESERVATIONS_ROUTE,
)
def portal_reservation_action(request, pk, action):
    if request.method != 'POST':
        return redirect(PORTAL_RESERVATIONS_ROUTE)

    reservation = get_object_or_404(Reservation, pk=pk)
    if action == 'cancel' and request.user.role == 'guest' and reservation.guest_id != request.user.id:
        messages.error(request, 'Guests can only cancel their own reservations.')
        return redirect(PORTAL_RESERVATIONS_ROUTE)

    action_map = {
        'confirm': ('pending', 'confirmed'),
        'check_in': ('confirmed', 'checked_in'),
        'check_out': ('checked_in', 'checked_out'),
        'cancel': (None, 'cancelled'),
    }

    is_valid_action, transition_error = _validate_reservation_transition(reservation, action, action_map)
    if not is_valid_action:
        messages.error(request, transition_error)
        return redirect(PORTAL_RESERVATIONS_ROUTE)

    _, next_status = action_map[action]

    with transaction.atomic():
        _apply_reservation_side_effects(reservation, action)

        reservation.status = next_status
        reservation.save()
        _send_reservation_action_notification(reservation, action)
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
@role_required({'admin', 'manager', 'receptionist'})
def portal_guests(request):
    guests = UserProfile.objects.filter(role='guest').order_by('first_name', 'last_name')
    return render(request, 'portals/guests.html', {'guests': guests, 'stats': _portal_stats(request.user)})


@login_required
def portal_billing(request):
    invoices = Invoice.objects.select_related('guest', 'reservation').order_by('-created_at')
    if request.user.role == 'guest':
        invoices = invoices.filter(guest=request.user)
    return render(request, 'portals/billing.html', {'invoices': invoices, 'stats': _portal_stats(request.user)})


@login_required
def portal_payments(request):
    can_manage = request.user.role in STAFF_ROLES
    payment_form = None
    if can_manage:
        payment_form = PaymentRecordForm(request.POST or None, user=request.user)
        if request.method == 'POST' and payment_form.is_valid():
            with transaction.atomic():
                payment = payment_form.save(commit=False)
                payment.processed_by = request.user
                payment.save()
                if payment.status == 'completed':
                    Receipt.objects.create(
                        invoice=payment.invoice,
                        amount=payment.amount,
                        notes=f'Auto-generated from payment {payment.reference}.',
                    )
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
                    },
                )
            messages.success(request, f'Payment {payment.reference} recorded successfully.')
            return redirect(PORTAL_PAYMENTS_ROUTE)

    payments = Payment.objects.select_related('invoice', 'processed_by').order_by('-created_at')
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
        task = task_form.save(commit=False)
        task.created_by = request.user
        task.save()
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

    transitions = {
        'confirm': ('pending', 'confirmed'),
        'start': ('confirmed', 'in_progress'),
        'complete': ('in_progress', 'completed'),
        'cancel': ('pending', 'cancelled'),
    }
    if action not in transitions:
        messages.error(request, 'Unknown service action.')
        return redirect(PORTAL_SERVICES_ROUTE)

    current, target = transitions[action]
    if order.status != current:
        messages.error(request, f'Cannot move order from {order.status} to {target}.')
        return redirect(PORTAL_SERVICES_ROUTE)

    order.status = target
    order.save(update_fields=['status', 'updated_at'])
    _notify_user(
        recipient=order.guest,
        title='Service order updated',
        message=f'Order {order.order_number} status is now {order.get_status_display()}.',
        notification_type='service',
        link=SERVICES_LINK,
    )
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
        'verify': {'admin', 'manager', 'housekeeping', 'receptionist'},
    },
    redirect_route=PORTAL_HOUSEKEEPING_ROUTE,
)
def portal_housekeeping_action(request, pk, action):
    if request.method != 'POST':
        return redirect(PORTAL_HOUSEKEEPING_ROUTE)

    task = get_object_or_404(HousekeepingTask, pk=pk)

    if action == 'start' and task.status == 'pending':
        task.status = 'in_progress'
        task.started_at = timezone.now()
        task.save(update_fields=['status', 'started_at', 'updated_at'])
    elif action == 'complete' and task.status in {'pending', 'in_progress'}:
        task.status = 'completed'
        task.completed_at = timezone.now()
        task.save(update_fields=['status', 'completed_at', 'updated_at'])
        if task.room.status == 'housekeeping':
            task.room.status = 'available'
            task.room.save(update_fields=['status'])
    elif action == 'verify' and task.status == 'completed':
        task.status = 'verified'
        task.save(update_fields=['status', 'updated_at'])
    else:
        messages.error(request, 'Invalid housekeeping status transition.')
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
@role_required({'admin', 'manager', 'receptionist'})
def portal_reports(request):
    selected_days = _selected_window_days(request)
    report, trend = _build_report_data(days=selected_days)
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
        },
    )


@login_required
@role_required({'admin', 'manager', 'receptionist'})
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
    writer.writerow(['Open Balance', report['open_balance']])
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
@role_required({'admin', 'manager', 'receptionist'})
def portal_reports_export_pdf(request):
    selected_days = _selected_window_days(request)
    report, trend = _build_report_data(days=selected_days)
    return _render_report_pdf(report, trend, days=selected_days)


@login_required
def portal_profile(request):
    return render(request, 'portals/profile.html', {'stats': _portal_stats(request.user)})


@login_required
def portal_notifications(request):
    notifications = Notification.objects.filter(recipient=request.user)
    notifications.filter(is_read=False).update(is_read=True)
    return render(request, 'portals/virtual-reality.html', {'notifications': notifications, 'stats': _portal_stats(request.user)})


@login_required
def portal_settings(request):
    return render(request, 'portals/rtl.html', {'stats': _portal_stats(request.user)})


def send_html_email(subject, template_name, context, recipient_list):
    html_content = render_to_string(template_name, context)
    text_content = strip_tags(html_content)
    email = EmailMultiAlternatives(
        subject=subject,
        body=text_content,
        from_email=None,
        to=recipient_list
    )
    email.attach_alternative(html_content, "text/html")
    try:
        email.send()
    except Exception as e:
        print(f"Error sending email {template_name}: {e}")


def generate_gdi_password():
    choices = string.ascii_lowercase + string.digits
    extra = ''.join(random.choice(choices) for _ in range(5))
    return f"GDI{extra}"


def portal_verify_booking(request):
    if 'booking_request_data' not in request.session or 'booking_verify_code' not in request.session:
        messages.error(request, 'No active booking verification found. Please initiate a booking first.')
        return redirect('frontend:public-home')
    
    booking_data = request.session['booking_request_data']
    correct_code = request.session['booking_verify_code']
    
    if request.method == 'POST':
        entered_code = request.POST.get('verification_code', '').strip()
        if entered_code == correct_code:
            email = booking_data['email'].lower().strip()
            first_name = booking_data['first_name'].strip()
            last_name = booking_data['last_name'].strip()
            phone = booking_data['phone'].strip()
            
            with transaction.atomic():
                user = UserProfile.objects.filter(email=email).first()
                new_password = None
                
                if not user:
                    base_username = email.split('@')[0] or 'guest'
                    username = base_username
                    index = 1
                    while UserProfile.objects.filter(username=username).exists():
                        username = f'{base_username}{index}'
                        index += 1
                        
                    new_password = generate_gdi_password()
                    
                    user = UserProfile.objects.create(
                        username=username,
                        email=email,
                        first_name=first_name,
                        last_name=last_name,
                        phone=phone,
                        role='guest',
                        is_active=True,
                    )
                    user.set_password(new_password)
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
                
                room = get_object_or_404(Room, id=booking_data['room_id'])
                reservation = Reservation.objects.create(
                    guest=user,
                    room=room,
                    check_in_date=booking_data['check_in_date'],
                    check_out_date=booking_data['check_out_date'],
                    num_adults=booking_data['num_adults'],
                    num_children=booking_data['num_children'],
                    special_requests=booking_data['special_requests'],
                    nightly_rate=room.current_price,
                    status='pending',
                    notes=f"Requested via website with email verification. Contact: {phone or 'N/A'}",
                    created_by=user,
                )
                
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
                send_html_email(
                    subject='GraceDay Inn - Booking Confirmed',
                    template_name='emails/booking_confirmed.html',
                    context={
                        'first_name': first_name,
                        'reservation_number': reservation.reservation_number,
                        'username': user.username,
                        'password': new_password,
                        'login_url': login_url,
                    },
                    recipient_list=[email],
                )
                
                login(request, user)
                
                del request.session['booking_request_data']
                del request.session['booking_verify_code']
                
                if new_password:
                    messages.success(request, f'Booking request {reservation.reservation_number} created! A portal account was created for you with password: {new_password}')
                else:
                    messages.success(request, f'Booking request {reservation.reservation_number} created! Welcome back.')
                    
                return redirect(PORTAL_DASHBOARD_ROUTE)
        else:
            messages.error(request, 'Invalid verification code. Please try again.')
            
    return render(request, 'portals/verify-booking.html', {'email': booking_data['email']})


def subscribe_newsletter(request):
    if request.method == 'POST':
        email = request.POST.get('email', '').strip().lower()
        if email:
            subscription, created = NewsletterSubscription.objects.get_or_create(email=email)
            if created or not subscription.is_active:
                subscription.is_active = True
                subscription.save()
                
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
