from django.db import models
from django.conf import settings
from django.utils import timezone
import uuid
from decimal import Decimal


def generate_reservation_number():
    year = timezone.now().year
    return f'GDI-{year}-{uuid.uuid4().hex[:10].upper()}'


class Reservation(models.Model):
    SOURCE_CHOICES = [
        ('direct_website', 'Direct Website'),
        ('front_desk', 'Front Desk'),
        ('phone', 'Phone'),
        ('walk_in', 'Walk In'),
        ('api', 'API'),
        ('admin', 'Administration'),
    ]
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
    rate_plan = models.ForeignKey(
        'rooms.RatePlan', on_delete=models.PROTECT, related_name='reservations',
        null=True, blank=True,
    )
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
    cancellation_fee = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    corporate_account = models.ForeignKey(
        'CorporateAccount', on_delete=models.PROTECT, null=True, blank=True,
        related_name='reservations',
    )
    group_booking = models.ForeignKey(
        'GroupBooking', on_delete=models.PROTECT, null=True, blank=True,
        related_name='reservations',
    )
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES, default='admin')
    channel_reference = models.CharField(max_length=100, blank=True)
    price_snapshot = models.JSONField(default=dict, blank=True)
    policy_snapshot = models.JSONField(default=dict, blank=True)
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
        if self._state.adding and not self.total_amount:
            nights = (self.check_out_date - self.check_in_date).days
            self.total_amount = Decimal(str(self.nightly_rate)) * max(nights, 1)
        super().save(*args, **kwargs)

    @property
    def nights(self):
        return (self.check_out_date - self.check_in_date).days


class ReservationStatusHistory(models.Model):
    reservation = models.ForeignKey(Reservation, on_delete=models.PROTECT, related_name='status_history')
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    action = models.CharField(max_length=30)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reservation_status_changes',
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']


class ReservationRoomAssignment(models.Model):
    reservation = models.ForeignKey(Reservation, on_delete=models.PROTECT, related_name='room_assignments')
    room = models.ForeignKey('rooms.Room', on_delete=models.PROTECT, related_name='reservation_assignments')
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='room_assignments_made',
    )
    assigned_at = models.DateTimeField(auto_now_add=True)
    released_at = models.DateTimeField(null=True, blank=True)
    reason = models.CharField(max_length=100, default='initial_assignment')

    class Meta:
        ordering = ['assigned_at', 'id']


class BookingQuote(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'), ('converted', 'Converted'),
        ('expired', 'Expired'), ('cancelled', 'Cancelled'),
    ]

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    guest = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='booking_quotes',
    )
    email = models.EmailField(blank=True)
    room = models.ForeignKey('rooms.Room', on_delete=models.PROTECT, related_name='booking_quotes')
    rate_plan = models.ForeignKey('rooms.RatePlan', on_delete=models.PROTECT, related_name='booking_quotes')
    check_in_date = models.DateField()
    check_out_date = models.DateField()
    num_adults = models.PositiveIntegerField(default=1)
    num_children = models.PositiveIntegerField(default=0)
    currency = models.CharField(max_length=3, default='NGN')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)
    tax_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2)
    promotion = models.ForeignKey(
        'rooms.Promotion', on_delete=models.PROTECT, null=True, blank=True,
        related_name='quotes',
    )
    discount_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    extra_total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    price_snapshot = models.JSONField(default=dict)
    policy_snapshot = models.JSONField(default=dict)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    expires_at = models.DateTimeField()
    converted_reservation = models.OneToOneField(
        Reservation, on_delete=models.PROTECT, null=True, blank=True, related_name='source_quote'
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_booking_quotes',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']


class InventoryHold(models.Model):
    STATUS_CHOICES = [
        ('active', 'Active'), ('converted', 'Converted'),
        ('released', 'Released'), ('expired', 'Expired'),
    ]

    quote = models.OneToOneField(BookingQuote, on_delete=models.CASCADE, related_name='hold')
    room = models.ForeignKey('rooms.Room', on_delete=models.PROTECT, related_name='inventory_holds')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    expires_at = models.DateTimeField()
    released_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['expires_at']


class BookingQuoteExtra(models.Model):
    quote = models.ForeignKey(BookingQuote, on_delete=models.PROTECT, related_name='selected_extras')
    extra = models.ForeignKey('rooms.BookableExtra', on_delete=models.PROTECT, related_name='quote_selections')
    quantity = models.PositiveIntegerField()
    unit_amount = models.DecimalField(max_digits=10, decimal_places=2)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['quote', 'extra'], name='unique_quote_extra'),
        ]


class ReservationAmendmentHistory(models.Model):
    reservation = models.ForeignKey(Reservation, on_delete=models.PROTECT, related_name='amendments')
    action = models.CharField(max_length=40)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    reason = models.CharField(max_length=255)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reservation_amendments_made',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']


class GuestCompanion(models.Model):
    reservation = models.ForeignKey(Reservation, on_delete=models.PROTECT, related_name='companions')
    full_name = models.CharField(max_length=160)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30, blank=True)
    nationality = models.CharField(max_length=80, blank=True)
    identity_type = models.CharField(max_length=50, blank=True)
    identity_last_four = models.CharField(max_length=4, blank=True)
    is_child = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']


class GuestConsentHistory(models.Model):
    guest = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='consent_history'
    )
    purpose = models.CharField(max_length=80)
    wording_version = models.CharField(max_length=50)
    granted = models.BooleanField()
    source = models.CharField(max_length=80)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='guest_consents_recorded',
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']


class WaitlistEntry(models.Model):
    STATUS_CHOICES = [
        ('waiting', 'Waiting'), ('offered', 'Offered'), ('converted', 'Converted'),
        ('expired', 'Expired'), ('cancelled', 'Cancelled'),
    ]
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    guest = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='waitlist_entries')
    room_type = models.ForeignKey('rooms.RoomType', on_delete=models.PROTECT, related_name='waitlist_entries')
    check_in_date = models.DateField()
    check_out_date = models.DateField()
    num_adults = models.PositiveIntegerField(default=1)
    num_children = models.PositiveIntegerField(default=0)
    priority = models.PositiveIntegerField(default=100)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='waiting')
    notes = models.TextField(blank=True)
    offered_at = models.DateTimeField(null=True, blank=True)
    offer_expires_at = models.DateTimeField(null=True, blank=True)
    converted_reservation = models.OneToOneField(
        Reservation, on_delete=models.PROTECT, null=True, blank=True,
        related_name='source_waitlist_entry',
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_waitlist_entries',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['priority', 'created_at']


class CorporateAccount(models.Model):
    STATUS_CHOICES = [('active', 'Active'), ('on_hold', 'On hold'), ('closed', 'Closed')]
    name = models.CharField(max_length=180, unique=True)
    account_code = models.SlugField(max_length=50, unique=True)
    billing_email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    address = models.TextField(blank=True)
    credit_limit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    payment_terms_days = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='active')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class GroupBooking(models.Model):
    STATUS_CHOICES = [('draft', 'Draft'), ('open', 'Open'), ('confirmed', 'Confirmed'), ('closed', 'Closed')]
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    name = models.CharField(max_length=180)
    corporate_account = models.ForeignKey(
        CorporateAccount, on_delete=models.PROTECT, null=True, blank=True,
        related_name='group_bookings',
    )
    arrival_date = models.DateField()
    departure_date = models.DateField()
    room_target = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='created_group_bookings',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def clean(self):
        if self.departure_date <= self.arrival_date:
            from django.core.exceptions import ValidationError
            raise ValidationError({'departure_date': 'Departure must be after arrival.'})

    def __str__(self):
        return f'{self.name} ({self.reference})'


class ReservationDiscountRequest(models.Model):
    STATUS_CHOICES = [('pending', 'Pending'), ('approved', 'Approved'), ('rejected', 'Rejected')]
    reservation = models.ForeignKey(Reservation, on_delete=models.PROTECT, related_name='discount_requests')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=255)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='requested_reservation_discounts'
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='reviewed_reservation_discounts',
    )
    review_note = models.CharField(max_length=255, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-requested_at']
