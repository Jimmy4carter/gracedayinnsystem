from django.contrib import admin
from .models import Reservation


@admin.register(Reservation)
class ReservationAdmin(admin.ModelAdmin):
    list_display = ['reservation_number', 'guest', 'room', 'check_in_date',
                    'check_out_date', 'status', 'total_amount']
    list_filter = ['status']
    search_fields = ['reservation_number', 'guest__username']
    readonly_fields = ['reservation_number', 'total_amount']
