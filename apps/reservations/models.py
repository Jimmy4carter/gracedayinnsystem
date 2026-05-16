from django.db import models
from django.conf import settings
from django.utils import timezone


def generate_reservation_number():
    from apps.reservations.models import Reservation
    year = timezone.now().year
    count = Reservation.objects.filter(created_at__year=year).count() + 1
    return f'GDI-{year}-{count:04d}'


class Reservation(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('checked_in', 'Checked In'),
        ('checked_out', 'Checked Out'),
        ('cancelled', 'Cancelled'),
        ('no_show', 'No Show'),
    ]

    reservation_number = models.CharField(max_length=20, unique=True, blank=True)
    guest = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                              related_name='reservations')
    room = models.ForeignKey('rooms.Room', on_delete=models.PROTECT,
                             related_name='reservations')
    check_in_date = models.DateField()
    check_out_date = models.DateField()
    actual_check_in = models.DateTimeField(null=True, blank=True)
    actual_check_out = models.DateTimeField(null=True, blank=True)
    num_adults = models.PositiveIntegerField(default=1)
    num_children = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    special_requests = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    nightly_rate = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='created_reservations')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reservation_number} - {self.guest.username}'

    def save(self, *args, **kwargs):
        if not self.reservation_number:
            self.reservation_number = generate_reservation_number()
        if not self.nightly_rate:
            self.nightly_rate = self.room.current_price
        nights = (self.check_out_date - self.check_in_date).days
        self.total_amount = self.nightly_rate * max(nights, 1)
        super().save(*args, **kwargs)

    @property
    def nights(self):
        return (self.check_out_date - self.check_in_date).days
