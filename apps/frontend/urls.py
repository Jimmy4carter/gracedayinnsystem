from django.urls import path
from . import views


app_name = 'frontend'


urlpatterns = [

    # =====================================================
    # PUBLIC WEBSITE
    # =====================================================

    path(
        '',
        views.home,
        name='public-home'
    ),

    path(
        'about/',
        views.about,
        name='public-about'
    ),

    path(
        'rooms/',
        views.public_rooms,
        name='public-rooms'
    ),

    path(
        'rooms/<int:pk>/',
        views.room_detail,
        name='public-room-detail'
    ),

    path(
        'blog/',
        views.blog,
        name='public-blog'
    ),

    path(
        'blog/details/',
        views.blog_detail,
        name='public-blog-detail'
    ),

    path(
        'offers/',
        views.public_offers,
        name='public-offers'
    ),

    path(
        'dining/',
        views.public_dining,
        name='public-dining'
    ),

    path(
        'laundry/',
        views.public_laundry,
        name='public-laundry'
    ),

    path(
        'contact/',
        views.contact,
        name='public-contact'
    ),

    path(
        'search/',
        views.public_search,
        name='public-search'
    ),


    # =====================================================
    # PORTAL AUTHENTICATION
    # =====================================================

    path(
        'portal/sign-in/',
        views.portal_sign_in,
        name='portal-sign-in'
    ),

    path(
        'portal/sign-up/',
        views.portal_sign_up,
        name='portal-sign-up'
    ),

    path(
        'portal/verify-booking/',
        views.portal_verify_booking,
        name='portal-verify-booking'
    ),

    path(
        'portal/logout/',
        views.portal_logout,
        name='portal-logout'
    ),


    # =====================================================
    # PORTAL DASHBOARD
    # =====================================================

    path(
        'portal/dashboard/',
        views.portal_dashboard,
        name='portal-dashboard'
    ),


    # =====================================================
    # HOTEL OPERATIONS
    # =====================================================

    # =====================================================
# ROOM MANAGEMENT
# =====================================================

# Room List
path(
    'portal/rooms/',
    views.portal_rooms,
    name='portal-rooms'
),

# View Room Details
path(
    'portal/rooms/<int:pk>/',
    views.portal_room_detail,
    name='portal-room-detail'
),

# Reserve / Book Room
path(
    'portal/rooms/<int:pk>/reserve/',
    views.portal_room_reserve,
    name='portal-room-reserve'
),

# Edit Room
path(
    'portal/rooms/<int:pk>/edit/',
    views.portal_room_edit,
    name='portal-room-edit'
),

# Delete Room
path(
    'portal/rooms/<int:pk>/delete/',
    views.portal_room_delete,
    name='portal-room-delete'
),

    path(
        'portal/reservations/',
        views.portal_reservations,
        name='portal-reservations'
    ),

    path(
        'portal/reservations/<int:pk>/<str:action>/',
        views.portal_reservation_action,
        name='portal-reservation-action'
    ),

    path(
        'portal/guests/',
        views.portal_guests,
        name='portal-guests'
    ),

    path(
        'portal/billing/',
        views.portal_billing,
        name='portal-billing'
    ),

    path(
        'portal/receipt/<int:invoice_id>/',
        views.portal_invoice_receipt,
        name='portal-invoice-print'
    ),

    path(
        'portal/payments/',
        views.portal_payments,
        name='portal-payments'
    ),

    path(
        'portal/services/',
        views.portal_services,
        name='portal-services'
    ),

    path(
        'portal/services/<int:pk>/<str:action>/',
        views.portal_service_action,
        name='portal-service-action'
    ),

    path(
        'portal/housekeeping/',
        views.portal_housekeeping,
        name='portal-housekeeping'
    ),

    path(
        'portal/housekeeping/<int:pk>/<str:action>/',
        views.portal_housekeeping_action,
        name='portal-housekeeping-action'
    ),


    # =====================================================
    # STAFF MANAGEMENT
    # =====================================================

    path(
        'portal/staff/',
        views.portal_staff,
        name='portal-staff'
    ),

    path(
        'portal/staff/<int:pk>/<str:action>/',
        views.portal_staff_action,
        name='portal-staff-action'
    ),


    # =====================================================
    # NEWSLETTER MANAGEMENT
    # =====================================================

    path(
        'portal/newsletter/',
        views.portal_newsletter,
        name='portal-newsletter'
    ),

    path(
        'portal/newsletter/<int:pk>/<str:action>/',
        views.portal_newsletter_action,
        name='portal-newsletter-action'
    ),


    # =====================================================
    # REPORTS
    # =====================================================

    path(
        'portal/reports/',
        views.portal_reports,
        name='portal-reports'
    ),

    path(
        'portal/reports/export/csv/',
        views.portal_reports_export_csv,
        name='portal-reports-export-csv'
    ),

    path(
        'portal/reports/export/pdf/',
        views.portal_reports_export_pdf,
        name='portal-reports-export-pdf'
    ),


    # =====================================================
    # USER ACCOUNT
    # =====================================================

    path(
        'portal/profile/',
        views.portal_profile,
        name='portal-profile'
    ),

    path(
        'portal/notifications/',
        views.portal_notifications,
        name='portal-notifications'
    ),

    path(
        'portal/settings/',
        views.portal_settings,
        name='portal-settings'
    ),


    # =====================================================
    # PUBLIC NEWSLETTER SUBSCRIPTION
    # =====================================================

    path(
        'subscribe-newsletter/',
        views.subscribe_newsletter,
        name='subscribe-newsletter'
    ),

]