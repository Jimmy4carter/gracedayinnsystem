from django.urls import path
from . import views


app_name = 'frontend'


urlpatterns = [
    path('robots.txt', views.robots_txt, name='robots-txt'),
    path('sitemap.xml', views.public_sitemap, name='public-sitemap'),

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
    path('local-guide/', views.public_guide, name='public-guide'),
    path('billboard/', views.public_billboard, name='public-billboard'),

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
    path('faq/', views.public_faq, name='public-faq'),
    path('policies/', views.public_policies, name='public-policies'),
    path('policies/<slug:slug>/', views.public_policy_detail, name='public-policy-detail'),
    path('portal/mfa/challenge/', views.portal_mfa_challenge, name='portal-mfa-challenge'),
    path('portal/mfa/enroll/', views.portal_mfa_enroll, name='portal-mfa-enroll'),
    path('booking/quote/', views.public_quote_confirm, name='public-quote-confirm'),
    path('chat/start/', views.chat_start, name='chat-start'),
    path('chat/<uuid:reference>/messages/', views.chat_messages, name='chat-messages'),
    path('chat/<uuid:reference>/send/', views.chat_send, name='chat-send'),
    path('chat/<uuid:reference>/feedback/', views.chat_feedback, name='chat-feedback'),

    path(
        'portal/password-reset/',
        views.portal_password_reset,
        name='portal-password-reset'
    ),

    path(
        'portal/set-password/<uidb64>/<token>/',
        views.portal_set_password,
        name='portal-set-password'
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
    path('portal/my-stay/', views.portal_my_stay, name='portal-my-stay'),
    path('portal/privacy/', views.portal_privacy, name='portal-privacy'),
    path(
        'portal/privacy/<int:pk>/download/',
        views.portal_privacy_download,
        name='portal-privacy-download',
    ),

    path(
        'portal/reservations/<int:pk>/manage/',
        views.portal_reservation_manage,
        name='portal-reservation-manage'
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
        'portal/front-desk/',
        views.portal_front_desk,
        name='portal-front-desk'
    ),
    path('portal/tape-chart/', views.portal_tape_chart, name='portal-tape-chart'),
    path('portal/commercial/', views.portal_commercial, name='portal-commercial'),

    path(
        'portal/payment-receipt/<int:receipt_id>/',
        views.portal_payment_receipt,
        name='portal-payment-receipt'
    ),

    path(
        'portal/cashier/',
        views.portal_cashier,
        name='portal-cashier'
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

    path('portal/maintenance/', views.portal_maintenance, name='portal-maintenance'),
    path(
        'portal/maintenance/<int:pk>/<str:action>/',
        views.portal_maintenance_action,
        name='portal-maintenance-action',
    ),
    path('portal/operations/', views.portal_operations, name='portal-operations'),
    path(
        'portal/operations/incidents/<int:pk>/<str:action>/',
        views.portal_incident_action, name='portal-incident-action',
    ),
    path(
        'portal/operations/lost-found/<int:pk>/<str:action>/',
        views.portal_lost_found_action, name='portal-lost-found-action',
    ),
    path('portal/operations/stock/', views.portal_stock, name='portal-stock'),


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
    path('portal/newsletter-message/<int:pk>/send/', views.portal_newsletter_send, name='portal-newsletter-send'),


    # =====================================================
    # REPORTS
    # =====================================================

    path(
        'portal/reports/',
        views.portal_reports,
        name='portal-reports'
    ),
    path('portal/financial-audit/', views.portal_financial_audit, name='portal-financial-audit'),

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
    path('portal/management/', views.portal_management, name='portal-management'),
    path('portal/management/packs/<int:pk>/<str:file_format>/', views.portal_management_pack_download, name='portal-management-pack-download'),
    path('portal/management/queries/<int:pk>/', views.portal_management_query, name='portal-management-query'),
    path('portal/management/night-audit/', views.portal_night_audit, name='portal-night-audit'),

    path('portal/inquiries/', views.portal_inquiries, name='portal-inquiries'),
    path('portal/inquiries/<int:pk>/', views.portal_inquiry_detail, name='portal-inquiry-detail'),
    path('portal/inquiry-attachments/<int:pk>/download/', views.portal_inquiry_attachment_download, name='portal-inquiry-attachment-download'),
    path('portal/chat/', views.portal_chat, name='portal-chat'),
    path('portal/chat/<uuid:reference>/', views.portal_chat_detail, name='portal-chat-detail'),

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
