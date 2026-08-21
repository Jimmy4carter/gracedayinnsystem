from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db.models.signals import post_save
from django.dispatch import receiver


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
    slug = models.SlugField(max_length=120, unique=True, blank=True)
    description = models.TextField(blank=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    max_occupancy = models.PositiveIntegerField(default=2)
    amenities = models.ManyToManyField(Amenity, blank=True)
    image = models.ImageField(upload_to='room_types/', blank=True, null=True)


    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.slug:
            from django.utils.text import slugify
            self.slug = slugify(self.name)
        return super().save(*args, **kwargs)


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
    price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True, help_text="Set a specific price for this room (overrides room type price)")
    image = models.ImageField(upload_to='rooms/', blank=True, null=True, help_text="Specific image for this room")
    amenities = models.ManyToManyField(Amenity, blank=True, help_text="Specific amenities for this room")
    is_active = models.BooleanField(default=True)
    is_sellable = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['number']

    def __str__(self):
        return f'Room {self.number} ({self.room_type.name})'

    @property
    def current_price(self):
        return self.price if self.price is not None else self.room_type.base_price


class RatePlan(models.Model):
    room_type = models.ForeignKey(RoomType, on_delete=models.PROTECT, related_name='rate_plans')
    name = models.CharField(max_length=120)
    code = models.SlugField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    inclusions = models.JSONField(default=list, blank=True)
    cancellation_policy = models.TextField(blank=True)
    deposit_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    min_stay = models.PositiveIntegerField(default=1)
    max_stay = models.PositiveIntegerField(default=30)
    included_adults = models.PositiveSmallIntegerField(default=1)
    extra_adult_per_night = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)]
    )
    child_per_night = models.DecimalField(
        max_digits=10, decimal_places=2, default=0, validators=[MinValueValidator(0)]
    )
    is_refundable = models.BooleanField(default=True)
    free_cancellation_hours = models.PositiveIntegerField(default=24)
    cancellation_fee_percent = models.DecimalField(
        max_digits=5, decimal_places=2, default=0,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['room_type__name', 'name']

    def __str__(self):
        return f'{self.room_type.name} — {self.name}'


class DailyRate(models.Model):
    rate_plan = models.ForeignKey(RatePlan, on_delete=models.CASCADE, related_name='daily_rates')
    date = models.DateField()
    price = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    min_stay = models.PositiveIntegerField(null=True, blank=True)
    closed_to_arrival = models.BooleanField(default=False)
    closed_to_departure = models.BooleanField(default=False)

    class Meta:
        ordering = ['date']
        constraints = [
            models.UniqueConstraint(fields=['rate_plan', 'date'], name='unique_daily_rate_plan_date'),
        ]


class TaxFee(models.Model):
    CALCULATION_CHOICES = [('percentage', 'Percentage'), ('fixed', 'Fixed per stay')]

    name = models.CharField(max_length=120)
    code = models.SlugField(max_length=50, unique=True)
    calculation = models.CharField(max_length=20, choices=CALCULATION_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    is_active = models.BooleanField(default=True)
    effective_from = models.DateField(null=True, blank=True)
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class RoomTypeImage(models.Model):
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, related_name='gallery_images')
    image = models.ImageField(upload_to='room_types/gallery/%Y/%m/')
    alt_text = models.CharField(max_length=180, help_text='Concise visual description for assistive technology.')
    caption = models.CharField(max_length=220, blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    is_featured = models.BooleanField(default=False)
    is_published = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['room_type'], condition=models.Q(is_featured=True),
                name='one_featured_image_per_room_type',
            ),
        ]

    def __str__(self):
        return f'{self.room_type.name} gallery image {self.pk or "new"}'


class RoomImage(models.Model):
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='gallery_images')
    image = models.ImageField(upload_to='rooms/gallery/%Y/%m/')
    alt_text = models.CharField(max_length=180, blank=True)
    caption = models.CharField(max_length=220, blank=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    is_featured = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['display_order', 'id']


class Promotion(models.Model):
    DISCOUNT_CHOICES = [('percentage', 'Percentage'), ('fixed', 'Fixed amount')]

    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    discount_type = models.CharField(max_length=20, choices=DISCOUNT_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    room_types = models.ManyToManyField(RoomType, blank=True, related_name='promotions')
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()
    minimum_nights = models.PositiveIntegerField(default=1)
    usage_limit = models.PositiveIntegerField(null=True, blank=True)
    times_used = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return self.code


class InventoryBlock(models.Model):
    STATUS_CHOICES = [('active', 'Active'), ('released', 'Released')]
    REASON_CHOICES = [
        ('maintenance', 'Maintenance'), ('owner_use', 'Owner use'),
        ('renovation', 'Renovation'), ('sales_stop', 'Sales stop'), ('other', 'Other'),
    ]
    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name='inventory_blocks')
    start_date = models.DateField()
    end_date = models.DateField(help_text='Exclusive end date.')
    reason = models.CharField(max_length=30, choices=REASON_CHOICES)
    notes = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    source_model = models.CharField(max_length=80, blank=True)
    source_id = models.CharField(max_length=80, blank=True)
    created_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_inventory_blocks',
    )
    released_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='released_inventory_blocks',
    )
    released_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['start_date', 'room__number']

    def clean(self):
        if self.end_date <= self.start_date:
            from django.core.exceptions import ValidationError
            raise ValidationError({'end_date': 'Inventory block end must be after its start.'})


class BookableExtra(models.Model):
    PRICING_CHOICES = [
        ('per_stay', 'Per stay'), ('per_night', 'Per night'),
        ('per_guest_per_night', 'Per guest per night'),
    ]
    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    pricing_model = models.CharField(max_length=30, choices=PRICING_CHOICES)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(0)])
    taxable = models.BooleanField(default=True)
    room_types = models.ManyToManyField(RoomType, blank=True, related_name='bookable_extras')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.code})'


@receiver(post_save, sender=RoomType)
def ensure_standard_rate_plan(sender, instance, created, **kwargs):
    if created:
        RatePlan.objects.get_or_create(
            code=f'standard-{instance.pk}',
            defaults={
                'room_type': instance,
                'name': 'Standard Rate',
                'description': 'Default flexible room rate.',
                'cancellation_policy': 'Contact the hotel for cancellation terms.',
            },
        )
