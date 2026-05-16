from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('login/', views.login_view, name='login'),
    path('rooms/', views.rooms_list, name='rooms'),
    path('reservations/', views.reservations_list, name='reservations'),
    path('billing/', views.billing_list, name='billing'),
    path('payments/', views.payments_list, name='payments'),
    path('services/', views.services_list, name='services'),
    path('housekeeping/', views.housekeeping_list, name='housekeeping'),
    path('guests/', views.guests_list, name='guests'),
]
