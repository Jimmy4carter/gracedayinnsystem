from django.shortcuts import render


def index(request):
    return render(request, 'frontend/index.html')

def login_view(request):
    return render(request, 'frontend/login.html')

def register_view(request):
    return render(request, 'frontend/register.html')

def dashboard(request):
    return render(request, 'frontend/dashboard.html')

def rooms_list(request):
    return render(request, 'frontend/rooms.html')

def reservations_list(request):
    return render(request, 'frontend/reservations.html')

def new_reservation(request):
    return render(request, 'frontend/new_reservation.html')

def reservation_detail(request, pk):
    return render(request, 'frontend/reservation_detail.html', {'reservation_id': pk})

def guests_list(request):
    return render(request, 'frontend/guests.html')

def billing_list(request):
    return render(request, 'frontend/billing.html')

def invoice_detail(request, pk):
    return render(request, 'frontend/invoice_detail.html', {'invoice_id': pk})

def payments_list(request):
    return render(request, 'frontend/payments.html')

def services_list(request):
    return render(request, 'frontend/services.html')

def restaurant_view(request):
    return render(request, 'frontend/restaurant.html')

def housekeeping_list(request):
    return render(request, 'frontend/housekeeping.html')

def reports_view(request):
    return render(request, 'frontend/reports.html')
