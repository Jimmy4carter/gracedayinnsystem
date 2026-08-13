import hashlib
import json
import uuid

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


class AuditLogQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise ValidationError('Audit records are append-only and cannot be updated.')

    def delete(self):
        raise ValidationError('Audit records are append-only and cannot be deleted.')


class AuditLogManager(models.Manager.from_queryset(AuditLogQuerySet)):
    def bulk_create(self, objs, **kwargs):
        raise ValidationError('Audit records must be appended individually to preserve the integrity chain.')


class AuditLog(models.Model):
	EVENT_CHOICES = [
		('reservation', 'Reservation'),
		('payment', 'Payment'),
		('housekeeping', 'Housekeeping'),
		('service', 'Service'),
		('security', 'Security'),
		('system', 'System'),
	]

	actor = models.ForeignKey(
		'accounts.UserProfile',
		on_delete=models.PROTECT,
		null=True,
		blank=True,
		related_name='audit_logs',
	)
	event_type = models.CharField(max_length=20, choices=EVENT_CHOICES)
	action = models.CharField(max_length=80)
	target_model = models.CharField(max_length=80)
	target_id = models.CharField(max_length=80, blank=True)
	details = models.JSONField(default=dict, blank=True)
	ip_address = models.GenericIPAddressField(null=True, blank=True)
	user_agent = models.CharField(max_length=255, blank=True)
	created_at = models.DateTimeField(default=timezone.now, editable=False)
	sequence = models.PositiveBigIntegerField(unique=True, editable=False)
	previous_hash = models.CharField(max_length=64, editable=False)
	event_hash = models.CharField(max_length=64, unique=True, editable=False)

	objects = AuditLogManager()

	class Meta:
		ordering = ['-created_at']

	def __str__(self):
		return f'{self.event_type}:{self.action} by {self.actor_id or "system"}'

	def canonical_payload(self):
		return {
			'sequence': self.sequence, 'previous_hash': self.previous_hash,
			'actor_id': self.actor_id, 'event_type': self.event_type, 'action': self.action,
			'target_model': self.target_model, 'target_id': self.target_id,
			'details': self.details, 'ip_address': self.ip_address,
			'user_agent': self.user_agent, 'created_at': self.created_at.isoformat(),
		}

	def calculate_hash(self):
		encoded = json.dumps(
			self.canonical_payload(), sort_keys=True, separators=(',', ':'), default=str,
		).encode('utf-8')
		return hashlib.sha256(encoded).hexdigest()

	def save(self, *args, **kwargs):
		if self.pk or self.__class__.objects.filter(pk=self.pk).exists():
			raise ValidationError('Audit records are append-only and cannot be updated.')
		from django.db import transaction
		with transaction.atomic():
			head, _ = AuditChainHead.objects.select_for_update().get_or_create(pk=1)
			self.sequence = head.last_sequence + 1
			self.previous_hash = head.last_hash
			self.event_hash = self.calculate_hash()
			super().save(*args, **kwargs)
			head.last_sequence = self.sequence
			head.last_hash = self.event_hash
			head.save(update_fields=['last_sequence', 'last_hash', 'updated_at'])

	def delete(self, *args, **kwargs):
		raise ValidationError('Audit records are append-only and cannot be deleted.')


class AuditChainHead(models.Model):
	id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
	last_sequence = models.PositiveBigIntegerField(default=0, editable=False)
	last_hash = models.CharField(max_length=64, default='0' * 64, editable=False)
	updated_at = models.DateTimeField(auto_now=True)

	def delete(self, *args, **kwargs):
		raise ValidationError('The audit chain head cannot be deleted.')

# Create your models here.

class NewsletterSubscription(models.Model):
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.email} (Active: {self.is_active})'


class SitePage(models.Model):
    path = models.CharField(max_length=180, unique=True, help_text='Public path, for example / or /rooms/.')
    navigation_title = models.CharField(max_length=80)
    browser_title = models.CharField(max_length=160)
    meta_description = models.CharField(max_length=300)
    hero_eyebrow = models.CharField(max_length=100, blank=True)
    hero_title = models.CharField(max_length=180, blank=True)
    hero_summary = models.TextField(blank=True)
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['path']

    def __str__(self):
        return f'{self.path} — {self.navigation_title}'

    def save(self, *args, **kwargs):
        if self.is_published and not self.published_at:
            self.published_at = timezone.now()
        elif not self.is_published:
            self.published_at = None
        return super().save(*args, **kwargs)


class SitePageTranslation(models.Model):
    page = models.ForeignKey(SitePage, on_delete=models.CASCADE, related_name='translations')
    language_code = models.CharField(max_length=10, help_text='BCP 47 language code, for example en, fr or ha.')
    navigation_title = models.CharField(max_length=80)
    browser_title = models.CharField(max_length=160)
    meta_description = models.CharField(max_length=300)
    hero_eyebrow = models.CharField(max_length=100, blank=True)
    hero_title = models.CharField(max_length=180, blank=True)
    hero_summary = models.TextField(blank=True)
    is_published = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['page', 'language_code'], name='unique_site_page_translation'),
        ]
        ordering = ['page', 'language_code']

    def save(self, *args, **kwargs):
        self.language_code = self.language_code.strip().lower()
        return super().save(*args, **kwargs)


class PolicyDocument(models.Model):
    TYPE_CHOICES = [
        ('privacy', 'Privacy notice'), ('booking', 'Booking terms'),
        ('cancellation', 'Cancellation policy'), ('cookies', 'Cookie notice'),
        ('accessibility', 'Accessibility statement'), ('house_rules', 'House rules'),
    ]
    REVIEW_CHOICES = [('draft', 'Draft'), ('approved', 'Approved')]

    slug = models.SlugField(max_length=80, unique=True)
    policy_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    title = models.CharField(max_length=180)
    summary = models.CharField(max_length=300)
    body = models.TextField(help_text='Plain text only. Paragraph breaks are preserved safely.')
    version = models.CharField(max_length=30, default='1.0')
    effective_date = models.DateField(null=True, blank=True)
    review_status = models.CharField(max_length=20, choices=REVIEW_CHOICES, default='draft')
    review_notes = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.PROTECT, null=True, blank=True,
        related_name='reviewed_policy_documents',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    approved_hash = models.CharField(max_length=64, blank=True, editable=False)
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['policy_type', 'title']

    def clean(self):
        if self.is_published and not (
            self.review_status == 'approved' and self.reviewed_by_id
            and self.reviewed_at and self.effective_date
        ):
            raise ValidationError('Only an approved, reviewed, effective-dated policy can be published.')
        if self.is_published and self.approved_hash != self.content_fingerprint():
            raise ValidationError('Policy content changed after approval and must be reviewed again.')

    def content_fingerprint(self):
        payload = json.dumps({
            'slug': self.slug, 'policy_type': self.policy_type, 'title': self.title,
            'summary': self.summary, 'body': self.body, 'version': self.version,
            'effective_date': self.effective_date.isoformat() if self.effective_date else '',
        }, sort_keys=True, separators=(',', ':'), ensure_ascii=False)
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def save(self, *args, **kwargs):
        reset_review = False
        if self.approved_hash and self.approved_hash != self.content_fingerprint():
            self.review_status = 'draft'
            self.reviewed_by = None
            self.reviewed_at = None
            self.approved_hash = ''
            self.is_published = False
            reset_review = True
        if not self.is_published:
            self.published_at = None
        if reset_review and kwargs.get('update_fields') is not None:
            kwargs['update_fields'] = set(kwargs['update_fields']) | {
                'review_status', 'reviewed_by', 'reviewed_at', 'approved_hash',
                'is_published', 'published_at', 'updated_at',
            }
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.title} v{self.version}'


class FAQItem(models.Model):
    CATEGORY_CHOICES = [
        ('booking', 'Booking'), ('stay', 'Your stay'), ('payment', 'Payment'),
        ('services', 'Hotel services'), ('accessibility', 'Accessibility'),
    ]
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES)
    question = models.CharField(max_length=220)
    answer = models.TextField()
    display_order = models.PositiveSmallIntegerField(default=0)
    is_published = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'display_order', 'id']

    def __str__(self):
        return self.question


class LocalGuidePlace(models.Model):
    CATEGORY_CHOICES = [
        ('landmark', 'Landmark'), ('dining', 'Dining'), ('shopping', 'Shopping'),
        ('business', 'Business'), ('transport', 'Transport'), ('wellness', 'Wellness'),
    ]
    name = models.CharField(max_length=140)
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    summary = models.TextField()
    address = models.CharField(max_length=255, blank=True)
    travel_minutes = models.PositiveSmallIntegerField(null=True, blank=True)
    website = models.URLField(blank=True)
    map_url = models.URLField(blank=True)
    image = models.ImageField(upload_to='local-guide/', blank=True, null=True)
    display_order = models.PositiveSmallIntegerField(default=0)
    is_published = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['display_order', 'name']

    def __str__(self):
        return self.name


class LocalGuidePlaceTranslation(models.Model):
    place = models.ForeignKey(LocalGuidePlace, on_delete=models.CASCADE, related_name='translations')
    language_code = models.CharField(max_length=10)
    name = models.CharField(max_length=140)
    summary = models.TextField()
    address = models.CharField(max_length=255, blank=True)
    is_published = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['place', 'language_code'], name='unique_guide_place_translation'),
        ]

    def save(self, *args, **kwargs):
        self.language_code = self.language_code.strip().lower()
        return super().save(*args, **kwargs)


class GuestTestimonial(models.Model):
    STATUS_CHOICES = [('pending', 'Pending review'), ('approved', 'Approved'), ('rejected', 'Rejected')]
    guest = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='testimonials',
    )
    reservation = models.ForeignKey(
        'reservations.Reservation', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='testimonials',
    )
    display_name = models.CharField(max_length=100)
    rating = models.PositiveSmallIntegerField()
    body = models.TextField(max_length=1500)
    publication_consent = models.BooleanField(default=False)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    moderation_notes = models.CharField(max_length=500, blank=True)
    reviewed_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reviewed_testimonials',
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def clean(self):
        if not 1 <= self.rating <= 5:
            raise ValidationError('Rating must be between 1 and 5.')
        if not self.publication_consent:
            raise ValidationError('Publication consent is required to submit a testimonial.')

    def __str__(self):
        return f'{self.display_name} ({self.rating}/5)'


class FeatureFlag(models.Model):
    key = models.SlugField(max_length=80, unique=True)
    description = models.CharField(max_length=255)
    is_enabled = models.BooleanField(default=False)
    roles = models.JSONField(default=list, blank=True, help_text='Empty means all roles.')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.key


class OperationalSetting(models.Model):
    key = models.SlugField(max_length=100, unique=True)
    value = models.JSONField(default=dict)
    description = models.CharField(max_length=255)
    is_secret = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.key


class AnalyticsEvent(models.Model):
    event_name = models.SlugField(max_length=80)
    path = models.CharField(max_length=255, blank=True)
    session_key = models.CharField(max_length=40, blank=True, db_index=True)
    user = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='analytics_events',
    )
    metadata = models.JSONField(default=dict, blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-occurred_at']
        indexes = [models.Index(fields=['event_name', 'occurred_at'], name='frontend_an_event_2d8d89_idx')]


class ManagementPack(models.Model):
    business_date = models.DateField(unique=True)
    metrics = models.JSONField(default=dict)
    booking_pace = models.JSONField(default=dict)
    exceptions = models.JSONField(default=dict)
    pdf_file = models.FileField(upload_to='management_packs/%Y/%m/')
    csv_file = models.FileField(upload_to='management_packs/%Y/%m/')
    generated_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='generated_management_packs',
    )
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-business_date']

    def save(self, *args, **kwargs):
        if self.pk and self.__class__.objects.filter(pk=self.pk).exists():
            raise ValidationError('Management packs are immutable; generate a replacement under controlled policy.')
        return super().save(*args, **kwargs)


class NewsletterMessage(models.Model):
    RECIPIENT_CHOICES = [
        ('all', 'All Subscribers'),
        ('active', 'Active Subscribers'),
    ]

    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('ready_to_send', 'Ready to Send'),
        ('sent', 'Sent'),
    ]

    subject = models.CharField(max_length=255)
    title = models.CharField(max_length=255)
    message = models.TextField()
    cta_text = models.CharField(max_length=100, blank=True)
    cta_link = models.URLField(blank=True)
    featured_image = models.ImageField(upload_to='newsletters/', blank=True, null=True)
    recipient = models.CharField(max_length=20, choices=RECIPIENT_CHOICES, default='all')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sent_at = models.DateTimeField(null=True, blank=True)
    recipient_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.subject} ({self.get_status_display()})'


class MetricDefinition(models.Model):
    key = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=160)
    description = models.TextField()
    formula = models.TextField()
    unit = models.CharField(max_length=30)
    source_models = models.JSONField(default=list)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)


class DailyMetricSnapshot(models.Model):
    business_date = models.DateField(unique=True)
    currency = models.CharField(max_length=3, default='NGN')
    available_rooms = models.PositiveIntegerField(default=0)
    occupied_rooms = models.PositiveIntegerField(default=0)
    occupancy_percent = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    room_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    service_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_revenue = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    adr = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    revpar = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    receivables = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    cash_variance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    reservation_sources = models.JSONField(default=dict)
    operational_sla = models.JSONField(default=dict)
    source_hash = models.CharField(max_length=64)
    generated_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='generated_metric_snapshots',
    )
    generated_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-business_date']

    def save(self, *args, **kwargs):
        if self.pk and self.__class__.objects.filter(pk=self.pk).exists():
            raise ValidationError('Daily metric snapshots are immutable.')
        return super().save(*args, **kwargs)


class NightAuditRun(models.Model):
    STATUS_CHOICES = [('completed', 'Completed'), ('reopened', 'Reopened')]
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    business_date = models.DateField(unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='completed')
    snapshot = models.OneToOneField(
        DailyMetricSnapshot, on_delete=models.PROTECT, related_name='night_audit'
    )
    exception_summary = models.JSONField(default=dict, blank=True)
    completed_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.PROTECT, related_name='completed_night_audits'
    )
    completed_at = models.DateTimeField(auto_now_add=True)
    reopened_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='reopened_night_audits',
    )
    reopened_at = models.DateTimeField(null=True, blank=True)
    reopen_reason = models.TextField(blank=True)

    class Meta:
        ordering = ['-business_date']


class ManagementQuery(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'), ('assigned', 'Assigned'), ('investigating', 'Investigating'),
        ('resolved', 'Resolved'), ('closed', 'Closed'),
    ]
    PRIORITY_CHOICES = [('normal', 'Normal'), ('high', 'High'), ('urgent', 'Urgent')]
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    title = models.CharField(max_length=200)
    description = models.TextField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='normal')
    source_model = models.CharField(max_length=80, blank=True)
    source_id = models.CharField(max_length=80, blank=True)
    raised_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.PROTECT, related_name='raised_management_queries'
    )
    assigned_to = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_management_queries',
    )
    due_at = models.DateTimeField(null=True, blank=True)
    resolution = models.TextField(blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']


class ManagementQueryNote(models.Model):
    query = models.ForeignKey(ManagementQuery, on_delete=models.PROTECT, related_name='notes')
    author = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='management_query_notes',
    )
    body = models.TextField()
    evidence = models.FileField(upload_to='management_queries/evidence/', null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']


class ManagementQueryHistory(models.Model):
    query = models.ForeignKey(ManagementQuery, on_delete=models.PROTECT, related_name='history')
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    action = models.CharField(max_length=30)
    actor = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='management_query_changes',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
