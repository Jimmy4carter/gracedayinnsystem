from django.shortcuts import render


def dashboard(request):
    return render(request, 'frontend/dashboard.html')


def rooms_list(request):
    return render(request, 'frontend/rooms.html')


def reservations_list(request):
    return render(request, 'frontend/reservations.html')


def billing_list(request):
    return render(request, 'frontend/billing.html')


def payments_list(request):
    return render(request, 'frontend/payments.html')


def services_list(request):
    return render(request, 'frontend/services.html')


def housekeeping_list(request):
    return render(request, 'frontend/housekeeping.html')


def guests_list(request):
    return render(request, 'frontend/guests.html')


def login_view(request):
    return render(request, 'frontend/login.html')
