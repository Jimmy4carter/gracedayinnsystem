from django.db import models
from django.utils import timezone


class ServiceCategory(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    icon = models.CharField(max_length=50, blank=True)

    class Meta:
        verbose_name_plural = 'Service Categories'

    def __str__(self):
        return self.name


class MenuItem(models.Model):
    category = models.ForeignKey(ServiceCategory, on_delete=models.PROTECT,
                                 related_name='menu_items')
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_available = models.BooleanField(default=True)
    image = models.ImageField(upload_to='menu/', blank=True, null=True)

    def __str__(self):
        return self.name


def generate_service_order_number():
    from apps.services.models import ServiceOrder
    year = timezone.now().year
    count = ServiceOrder.objects.filter(created_at__year=year).count() + 1
    return f'SVC-{year}-{count:04d}'


class ServiceOrder(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('confirmed', 'Confirmed'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('cancelled', 'Cancelled'),
    ]

    order_number = models.CharField(max_length=20, unique=True, blank=True)
    reservation = models.ForeignKey('reservations.Reservation', on_delete=models.PROTECT,
                                    related_name='service_orders', null=True, blank=True)
    guest = models.ForeignKey('accounts.UserProfile', on_delete=models.PROTECT,
                              related_name='service_orders')
    room = models.ForeignKey('rooms.Room', on_delete=models.PROTECT,
                             related_name='service_orders', null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    notes = models.TextField(blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.order_number}'

    def save(self, *args, **kwargs):
        if not self.order_number:
            self.order_number = generate_service_order_number()
        super().save(*args, **kwargs)

    def recalculate_total(self):
        self.total = sum(item.subtotal for item in self.items.all())
        self.__class__.objects.filter(pk=self.pk).update(total=self.total)


class ServiceOrderItem(models.Model):
    order = models.ForeignKey(ServiceOrder, on_delete=models.CASCADE, related_name='items')
    menu_item = models.ForeignKey(MenuItem, on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField(default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        self.unit_price = self.menu_item.price
        self.subtotal = self.unit_price * self.quantity
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.menu_item.name} x{self.quantity}'
