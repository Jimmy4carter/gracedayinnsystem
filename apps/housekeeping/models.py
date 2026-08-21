import uuid

from django.core.exceptions import ValidationError
from django.db import models


class HousekeepingTask(models.Model):
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('verified', 'Verified'),
    ]
    TASK_TYPE_CHOICES = [
        ('cleaning', 'Room Cleaning'),
        ('turndown', 'Turndown Service'),
        ('deep_clean', 'Deep Cleaning'),
        ('maintenance', 'Maintenance Check'),
        ('inspection', 'Inspection'),
        ('other', 'Other'),
    ]

    room = models.ForeignKey('rooms.Room', on_delete=models.PROTECT,
                             related_name='housekeeping_tasks')
    task_type = models.CharField(max_length=20, choices=TASK_TYPE_CHOICES, default='cleaning')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    assigned_to = models.ForeignKey('accounts.UserProfile', on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='assigned_tasks')
    notes = models.TextField(blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    verified_at = models.DateTimeField(null=True, blank=True)
    verified_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='verified_housekeeping_tasks',
    )
    completion_notes = models.TextField(blank=True)
    inspection_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey('accounts.UserProfile', on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='created_tasks')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_task_type_display()} - Room {self.room.number}'


class HousekeepingTaskHistory(models.Model):
    task = models.ForeignKey(HousekeepingTask, on_delete=models.PROTECT, related_name='history')
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    action = models.CharField(max_length=30)
    actor = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='housekeeping_task_changes',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def save(self, *args, **kwargs):
        if self.pk and self.__class__.objects.filter(pk=self.pk).exists():
            raise ValidationError('Housekeeping history is immutable.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Housekeeping history cannot be deleted.')


class MaintenanceTicket(models.Model):
    STATUS_CHOICES = [
        ('reported', 'Reported'), ('in_progress', 'In Progress'),
        ('resolved', 'Resolved — Awaiting Approval'), ('approved', 'Returned to Service'),
        ('cancelled', 'Cancelled'),
    ]
    PRIORITY_CHOICES = HousekeepingTask.PRIORITY_CHOICES

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    room = models.ForeignKey('rooms.Room', on_delete=models.PROTECT, related_name='maintenance_tickets')
    category = models.CharField(max_length=80, default='general')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='reported')
    title = models.CharField(max_length=160)
    description = models.TextField()
    downtime_required = models.BooleanField(default=True)
    evidence = models.ImageField(upload_to='maintenance/evidence/', null=True, blank=True)
    assigned_to = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_maintenance_tickets',
    )
    reported_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reported_maintenance_tickets',
    )
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    resolution_notes = models.TextField(blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    approved_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_maintenance_tickets',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']


class MaintenanceTicketHistory(models.Model):
    ticket = models.ForeignKey(MaintenanceTicket, on_delete=models.PROTECT, related_name='history')
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    action = models.CharField(max_length=30)
    actor = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='maintenance_ticket_changes',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def save(self, *args, **kwargs):
        if self.pk and self.__class__.objects.filter(pk=self.pk).exists():
            raise ValidationError('Maintenance history is immutable.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Maintenance history cannot be deleted.')


class IncidentReport(models.Model):
    TYPE_CHOICES = [
        ('safety', 'Safety'), ('security', 'Security'), ('guest', 'Guest related'),
        ('financial', 'Financial'), ('privacy', 'Privacy'), ('other', 'Other'),
    ]
    SEVERITY_CHOICES = [('low', 'Low'), ('medium', 'Medium'), ('high', 'High'), ('critical', 'Critical')]
    STATUS_CHOICES = [
        ('open', 'Open'), ('investigating', 'Investigating'),
        ('resolved', 'Resolved'), ('closed', 'Closed'),
    ]

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    incident_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    title = models.CharField(max_length=180)
    description = models.TextField()
    location = models.CharField(max_length=160)
    occurred_at = models.DateTimeField()
    room = models.ForeignKey(
        'rooms.Room', on_delete=models.PROTECT, null=True, blank=True, related_name='incident_reports',
    )
    reservation = models.ForeignKey(
        'reservations.Reservation', on_delete=models.PROTECT, null=True, blank=True,
        related_name='incident_reports',
    )
    reported_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.PROTECT, related_name='reported_incidents',
    )
    assigned_to = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_incidents',
    )
    resolution = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']


class IncidentReportHistory(models.Model):
    incident = models.ForeignKey(IncidentReport, on_delete=models.PROTECT, related_name='history')
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    action = models.CharField(max_length=30)
    actor = models.ForeignKey('accounts.UserProfile', on_delete=models.PROTECT, related_name='incident_changes')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def save(self, *args, **kwargs):
        if self.pk and self.__class__.objects.filter(pk=self.pk).exists():
            raise ValidationError('Incident history is immutable.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Incident history cannot be deleted.')


class LostFoundItem(models.Model):
    STATUS_CHOICES = [
        ('found', 'Found'), ('stored', 'Stored securely'), ('claimed', 'Claim recorded'),
        ('returned', 'Returned'), ('disposed', 'Disposed'),
    ]

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='found')
    item_name = models.CharField(max_length=160)
    description = models.TextField()
    found_location = models.CharField(max_length=160)
    found_at = models.DateTimeField()
    room = models.ForeignKey(
        'rooms.Room', on_delete=models.PROTECT, null=True, blank=True, related_name='lost_found_items',
    )
    found_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.PROTECT, related_name='found_items',
    )
    storage_location = models.CharField(max_length=160, blank=True)
    claimant_name = models.CharField(max_length=160, blank=True)
    claimant_contact = models.CharField(max_length=160, blank=True)
    claim_verification = models.TextField(blank=True)
    disposition_notes = models.TextField(blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    completed_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.PROTECT, null=True, blank=True,
        related_name='completed_lost_found_items',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']


class LostFoundItemHistory(models.Model):
    item = models.ForeignKey(LostFoundItem, on_delete=models.PROTECT, related_name='history')
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    action = models.CharField(max_length=30)
    actor = models.ForeignKey('accounts.UserProfile', on_delete=models.PROTECT, related_name='lost_found_changes')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def save(self, *args, **kwargs):
        if self.pk and self.__class__.objects.filter(pk=self.pk).exists():
            raise ValidationError('Lost-and-found history is immutable.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Lost-and-found history cannot be deleted.')


class StockLocation(models.Model):
    TYPE_CHOICES = [
        ('main_store', 'Main store'), ('floor_store', 'Floor store'),
        ('front_desk', 'Front desk'), ('outlet', 'Outlet'), ('other', 'Other'),
    ]
    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=120)
    location_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class StockItem(models.Model):
    CATEGORY_CHOICES = [
        ('linen', 'Linen'), ('minibar', 'Minibar'), ('housekeeping', 'Housekeeping supply'),
        ('maintenance', 'Maintenance supply'), ('other', 'Other'),
    ]
    sku = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=140)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    unit = models.CharField(max_length=30, default='each')
    reorder_level = models.DecimalField(max_digits=12, decimal_places=3, default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['category', 'name']

    def __str__(self):
        return f'{self.name} ({self.sku})'


class StockBalance(models.Model):
    item = models.ForeignKey(StockItem, on_delete=models.PROTECT, related_name='balances')
    location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name='balances')
    quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['location__name', 'item__name']
        constraints = [
            models.UniqueConstraint(fields=['item', 'location'], name='unique_item_location_balance'),
            models.CheckConstraint(check=models.Q(quantity__gte=0), name='stock_balance_not_negative'),
        ]


class StockMovement(models.Model):
    TYPE_CHOICES = [
        ('receipt', 'Receipt'), ('issue', 'Issue'), ('waste', 'Waste'),
        ('adjustment_add', 'Positive adjustment'), ('adjustment_remove', 'Negative adjustment'),
        ('transfer_in', 'Transfer in'), ('transfer_out', 'Transfer out'),
    ]
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    item = models.ForeignKey(StockItem, on_delete=models.PROTECT, related_name='movements')
    location = models.ForeignKey(StockLocation, on_delete=models.PROTECT, related_name='movements')
    movement_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    quantity_delta = models.DecimalField(max_digits=14, decimal_places=3)
    resulting_balance = models.DecimalField(max_digits=14, decimal_places=3)
    transfer_reference = models.UUIDField(null=True, blank=True, db_index=True)
    reason = models.CharField(max_length=255)
    actor = models.ForeignKey('accounts.UserProfile', on_delete=models.PROTECT, related_name='stock_movements')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at', '-id']

    def save(self, *args, **kwargs):
        if self.pk and self.__class__.objects.filter(pk=self.pk).exists():
            raise ValidationError('Stock movements are immutable.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Stock movements cannot be deleted.')
