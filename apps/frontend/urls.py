from django.urls import path
from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('login/', views.login_view, name='login'),
    path('register/', views.register_view, name='register'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('rooms/', views.rooms_list, name='rooms'),
    path('reservations/', views.reservations_list, name='reservations'),
    path('reservations/new/', views.new_reservation, name='new-reservation'),
    path('reservations/<int:pk>/', views.reservation_detail, name='reservation-detail'),
    path('guests/', views.guests_list, name='guests'),
    path('billing/', views.billing_list, name='billing'),
    path('billing/<int:pk>/', views.invoice_detail, name='invoice-detail'),
    path('payments/', views.payments_list, name='payments'),
    path('services/', views.services_list, name='services'),
    path('restaurant/', views.restaurant_view, name='restaurant'),
    path('housekeeping/', views.housekeeping_list, name='housekeeping'),
    path('reports/', views.reports_view, name='reports'),
]
