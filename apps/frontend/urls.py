from django.urls import path
from . import views

app_name = 'frontend'

urlpatterns = [
    path('', views.home, name='public-home'),
    path('about/', views.about, name='public-about'),
    path('rooms/', views.public_rooms, name='public-rooms'),
    path('rooms/<int:pk>/', views.room_detail, name='public-room-detail'),
    path('blog/', views.blog, name='public-blog'),
    path('blog/details/', views.blog_detail, name='public-blog-detail'),
    path('offers/', views.public_offers, name='public-offers'),
    path('dining/', views.public_dining, name='public-dining'),
    path('laundry/', views.public_laundry, name='public-laundry'),
    path('contact/', views.contact, name='public-contact'),
    path('search/', views.public_search, name='public-search'),

    path('portal/sign-in/', views.portal_sign_in, name='portal-sign-in'),
    path('portal/sign-up/', views.portal_sign_up, name='portal-sign-up'),
    path('portal/verify-booking/', views.portal_verify_booking, name='portal-verify-booking'),
    path('portal/logout/', views.portal_logout, name='portal-logout'),
    path('portal/dashboard/', views.portal_dashboard, name='portal-dashboard'),
    path('portal/rooms/', views.portal_rooms, name='portal-rooms'),
    path('portal/reservations/', views.portal_reservations, name='portal-reservations'),
    path('portal/reservations/<int:pk>/<str:action>/', views.portal_reservation_action, name='portal-reservation-action'),
    path('portal/guests/', views.portal_guests, name='portal-guests'),
    path('portal/billing/', views.portal_billing, name='portal-billing'),
    path('portal/payments/', views.portal_payments, name='portal-payments'),
    path('portal/services/', views.portal_services, name='portal-services'),
    path('portal/services/<int:pk>/<str:action>/', views.portal_service_action, name='portal-service-action'),
    path('portal/housekeeping/', views.portal_housekeeping, name='portal-housekeeping'),
    path('portal/housekeeping/<int:pk>/<str:action>/', views.portal_housekeeping_action, name='portal-housekeeping-action'),
    path('portal/reports/', views.portal_reports, name='portal-reports'),
    path('portal/reports/export/csv/', views.portal_reports_export_csv, name='portal-reports-export-csv'),
    path('portal/reports/export/pdf/', views.portal_reports_export_pdf, name='portal-reports-export-pdf'),
    path('portal/profile/', views.portal_profile, name='portal-profile'),
    path('portal/notifications/', views.portal_notifications, name='portal-notifications'),
    path('portal/settings/', views.portal_settings, name='portal-settings'),
    path('subscribe-newsletter/', views.subscribe_newsletter, name='subscribe-newsletter'),
]
