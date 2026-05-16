from django.db import models


class Amenity(models.Model):
    name = models.CharField(max_length=100)
    icon = models.CharField(max_length=50, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = 'Amenities'

    def __str__(self):
        return self.name


class RoomType(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    max_occupancy = models.PositiveIntegerField(default=2)
    amenities = models.ManyToManyField(Amenity, blank=True)
    image = models.ImageField(upload_to='room_types/', blank=True, null=True)

    def __str__(self):
        return self.name


class Room(models.Model):
    STATUS_CHOICES = [
        ('available', 'Available'),
        ('occupied', 'Occupied'),
        ('housekeeping', 'Housekeeping'),
        ('maintenance', 'Maintenance'),
        ('out_of_order', 'Out of Order'),
    ]
    FLOOR_CHOICES = [(i, f'Floor {i}') for i in range(1, 11)]

    number = models.CharField(max_length=10, unique=True)
    room_type = models.ForeignKey(RoomType, on_delete=models.PROTECT, related_name='rooms')
    floor = models.PositiveIntegerField(choices=FLOOR_CHOICES, default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='available')
    description = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['number']

    def __str__(self):
        return f'Room {self.number} ({self.room_type.name})'

    @property
    def current_price(self):
        return self.room_type.base_price
