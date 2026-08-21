import uuid

from django.core.exceptions import ValidationError
from django.db import models


class Notification(models.Model):
    TYPE_CHOICES = [
        ('reservation', 'Reservation'),
        ('payment', 'Payment'),
        ('housekeeping', 'Housekeeping'),
        ('service', 'Service'),
        ('system', 'System'),
        ('general', 'General'),
    ]

    recipient = models.ForeignKey('accounts.UserProfile', on_delete=models.CASCADE,
                                  related_name='notifications')
    title = models.CharField(max_length=200)
    message = models.TextField()
    notification_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default='general')
    is_read = models.BooleanField(default=False)
    link = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} -> {self.recipient.username}'


class AlertRule(models.Model):
    TYPE_CHOICES = [
        ('room_state', 'Room-state discrepancy'),
        ('overdue_housekeeping', 'Overdue housekeeping'),
        ('overdue_maintenance', 'Overdue maintenance'),
        ('unanswered_chat', 'Unanswered live chat'),
        ('inquiry_sla', 'Inquiry SLA breach'),
        ('job_failure', 'Scheduled-job failures'),
    ]
    SEVERITY_CHOICES = [('info', 'Info'), ('warning', 'Warning'), ('high', 'High'), ('critical', 'Critical')]
    key = models.SlugField(max_length=80, unique=True)
    name = models.CharField(max_length=160)
    rule_type = models.CharField(max_length=40, choices=TYPE_CHOICES)
    is_enabled = models.BooleanField(default=True)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='warning')
    threshold_minutes = models.PositiveIntegerField(default=60)
    recipient_roles = models.JSONField(default=list, blank=True)
    configuration = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['key']

    def __str__(self):
        return self.name


class OperationalAlert(models.Model):
    STATUS_CHOICES = [('open', 'Open'), ('acknowledged', 'Acknowledged'), ('resolved', 'Resolved')]
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    rule = models.ForeignKey(AlertRule, on_delete=models.PROTECT, related_name='alerts')
    dedupe_key = models.CharField(max_length=180, unique=True)
    title = models.CharField(max_length=200)
    detail = models.TextField()
    severity = models.CharField(max_length=20, choices=AlertRule.SEVERITY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    source_model = models.CharField(max_length=80)
    source_id = models.CharField(max_length=80)
    link = models.CharField(max_length=200, blank=True)
    occurrence_count = models.PositiveIntegerField(default=1)
    first_detected_at = models.DateTimeField(auto_now_add=True)
    last_detected_at = models.DateTimeField(auto_now_add=True)
    acknowledged_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='acknowledged_operational_alerts',
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='resolved_operational_alerts',
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_notes = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ['status', '-severity', '-last_detected_at']


class OperationalAlertHistory(models.Model):
    alert = models.ForeignKey(OperationalAlert, on_delete=models.PROTECT, related_name='history')
    action = models.CharField(max_length=30)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    actor = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='operational_alert_actions',
    )
    notes = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def save(self, *args, **kwargs):
        if self.pk and self.__class__.objects.filter(pk=self.pk).exists():
            raise ValidationError('Operational alert history is immutable.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Operational alert history cannot be deleted.')


class CommunicationTemplate(models.Model):
    STATUS_CHOICES = [('draft', 'Draft'), ('published', 'Published'), ('retired', 'Retired')]
    CHANNEL_CHOICES = [('email', 'Email')]

    key = models.SlugField(max_length=100)
    channel = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='email')
    locale = models.CharField(max_length=10, default='en')
    version = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    subject = models.CharField(max_length=255)
    html_body = models.TextField()
    text_body = models.TextField(blank=True)
    variables_schema = models.JSONField(default=dict, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['key', 'locale', 'version'], name='unique_template_version')]
        ordering = ['key', 'locale', '-version']


class OutboundMessage(models.Model):
    STATUS_CHOICES = [
        ('queued', 'Queued'), ('processing', 'Processing'), ('accepted', 'Accepted'),
        ('delivered', 'Delivered'), ('deferred', 'Deferred'), ('failed', 'Failed'),
        ('bounced', 'Bounced'), ('complained', 'Complained'), ('suppressed', 'Suppressed'),
    ]

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    purpose = models.CharField(max_length=80)
    recipient = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='outbound_messages',
    )
    recipient_email = models.EmailField()
    recipient_name = models.CharField(max_length=160, blank=True)
    template = models.ForeignKey(
        CommunicationTemplate, on_delete=models.PROTECT, null=True, blank=True,
        related_name='messages',
    )
    subject = models.CharField(max_length=255)
    html_body = models.TextField()
    text_body = models.TextField(blank=True)
    context = models.JSONField(default=dict, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    provider = models.CharField(max_length=30, default='brevo')
    provider_message_id = models.CharField(max_length=255, blank=True, db_index=True)
    idempotency_key = models.CharField(max_length=120, unique=True)
    related_model = models.CharField(max_length=80, blank=True)
    related_id = models.CharField(max_length=80, blank=True)
    attempt_count = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']


class DeliveryAttempt(models.Model):
    message = models.ForeignKey(OutboundMessage, on_delete=models.PROTECT, related_name='attempts')
    attempt_number = models.PositiveIntegerField()
    outcome = models.CharField(max_length=30)
    response_code = models.PositiveIntegerField(null=True, blank=True)
    provider_message_id = models.CharField(max_length=255, blank=True)
    error_detail = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['message', 'attempt_number'], name='unique_delivery_attempt')]


class DeliveryEvent(models.Model):
    EVENT_CHOICES = [
        ('sent', 'Sent'), ('delivered', 'Delivered'), ('opened', 'Opened'),
        ('clicked', 'Clicked'), ('deferred', 'Deferred'), ('soft_bounce', 'Soft Bounce'),
        ('hard_bounce', 'Hard Bounce'), ('blocked', 'Blocked'), ('invalid', 'Invalid'),
        ('complaint', 'Complaint'), ('unsubscribed', 'Unsubscribed'), ('error', 'Error'),
    ]
    provider_event_id = models.CharField(max_length=160, unique=True)
    message = models.ForeignKey(OutboundMessage, on_delete=models.PROTECT, related_name='events', null=True, blank=True)
    event_type = models.CharField(max_length=30, choices=EVENT_CHOICES)
    provider_message_id = models.CharField(max_length=255, blank=True)
    recipient_email = models.EmailField(blank=True)
    occurred_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    received_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-received_at']


class ContactPreference(models.Model):
    email = models.EmailField()
    purpose = models.CharField(max_length=50, default='marketing')
    consent_granted = models.BooleanField(default=False)
    consent_source = models.CharField(max_length=100)
    consent_version = models.CharField(max_length=50, blank=True)
    granted_at = models.DateTimeField(null=True, blank=True)
    withdrawn_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['email', 'purpose'], name='unique_contact_preference')]


class Suppression(models.Model):
    REASON_CHOICES = [
        ('unsubscribe', 'Unsubscribe'), ('complaint', 'Complaint'),
        ('hard_bounce', 'Hard Bounce'), ('invalid', 'Invalid Address'), ('manual', 'Manual'),
    ]
    email = models.EmailField(unique=True)
    reason = models.CharField(max_length=30, choices=REASON_CHOICES)
    source = models.CharField(max_length=50, default='brevo')
    created_at = models.DateTimeField(auto_now_add=True)


class BrevoContactSync(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'), ('synced', 'Synced'), ('deferred', 'Deferred'),
        ('failed', 'Failed'), ('suppressed', 'Suppressed'),
    ]
    email = models.EmailField(unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    desired_marketing_consent = models.BooleanField(default=False)
    attempt_count = models.PositiveIntegerField(default=0)
    provider_contact_id = models.CharField(max_length=80, blank=True)
    last_error = models.CharField(max_length=500, blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['status', 'email']


class InquiryCase(models.Model):
    CATEGORY_CHOICES = [
        ('reservation', 'Reservation'), ('corporate', 'Corporate/Group'),
        ('event', 'Event'), ('service', 'Service'), ('billing', 'Billing'),
        ('complaint', 'Complaint'), ('general', 'General'),
    ]
    STATUS_CHOICES = [
        ('new', 'New'), ('acknowledged', 'Acknowledged'), ('in_progress', 'In Progress'),
        ('awaiting_guest', 'Awaiting Guest'), ('resolved', 'Resolved'),
        ('closed', 'Closed'), ('spam', 'Spam'),
    ]
    PRIORITY_CHOICES = [('low', 'Low'), ('normal', 'Normal'), ('high', 'High'), ('urgent', 'Urgent')]

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    category = models.CharField(max_length=30, choices=CATEGORY_CHOICES, default='general')
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default='new')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='normal')
    subject = models.CharField(max_length=255)
    requester_name = models.CharField(max_length=160)
    requester_email = models.EmailField()
    requester = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inquiry_cases',
    )
    owner = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='owned_inquiry_cases',
    )
    reservation = models.ForeignKey(
        'reservations.Reservation', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inquiry_cases',
    )
    source = models.CharField(max_length=30, default='website')
    first_response_due_at = models.DateTimeField(null=True, blank=True)
    resolution_due_at = models.DateTimeField(null=True, blank=True)
    first_responded_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    outcome = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']


class InquiryMessage(models.Model):
    case = models.ForeignKey(InquiryCase, on_delete=models.PROTECT, related_name='messages')
    sender = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inquiry_messages',
    )
    sender_name = models.CharField(max_length=160, blank=True)
    sender_email = models.EmailField(blank=True)
    body = models.TextField()
    is_internal = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']


class InquiryStatusHistory(models.Model):
    case = models.ForeignKey(InquiryCase, on_delete=models.PROTECT, related_name='history')
    from_status = models.CharField(max_length=30, blank=True)
    to_status = models.CharField(max_length=30)
    action = models.CharField(max_length=40)
    actor = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inquiry_case_changes',
    )
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def save(self, *args, **kwargs):
        if self.pk and self.__class__.objects.filter(pk=self.pk).exists():
            raise ValidationError('Inquiry history is immutable.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Inquiry history cannot be deleted.')


class InquiryRoutingRule(models.Model):
    name = models.CharField(max_length=120)
    category = models.CharField(max_length=30, choices=InquiryCase.CATEGORY_CHOICES)
    source = models.CharField(max_length=30, blank=True, help_text='Blank matches every source.')
    priority = models.CharField(max_length=20, choices=InquiryCase.PRIORITY_CHOICES, default='normal')
    owner = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.PROTECT, null=True, blank=True,
        related_name='inquiry_routing_rules',
    )
    first_response_hours = models.PositiveSmallIntegerField(default=4)
    resolution_hours = models.PositiveSmallIntegerField(default=48)
    order = models.PositiveSmallIntegerField(default=100)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ['order', 'id']


class InquiryAttachment(models.Model):
    case = models.ForeignKey(InquiryCase, on_delete=models.PROTECT, related_name='attachments')
    file = models.FileField(upload_to='protected/inquiries/%Y/%m/')
    original_name = models.CharField(max_length=255)
    content_type = models.CharField(max_length=100)
    size = models.PositiveIntegerField()
    uploaded_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inquiry_attachments',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def save(self, *args, **kwargs):
        if self.pk and self.__class__.objects.filter(pk=self.pk).exists():
            raise ValidationError('Inquiry attachments are immutable.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Inquiry attachments cannot be deleted from case history.')


class ChatConversation(models.Model):
    STATUS_CHOICES = [
        ('queued', 'Queued'), ('open', 'Open'), ('waiting', 'Waiting for Guest'),
        ('closed', 'Closed'), ('spam', 'Spam'),
    ]
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    visitor_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    guest = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='chat_conversations',
    )
    visitor_name = models.CharField(max_length=160, blank=True)
    visitor_email = models.EmailField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    queue = models.CharField(max_length=50, default='front_desk')
    assigned_to = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='assigned_chat_conversations',
    )
    inquiry = models.ForeignKey(
        InquiryCase, on_delete=models.SET_NULL, null=True, blank=True, related_name='chat_conversations'
    )
    reservation = models.ForeignKey(
        'reservations.Reservation', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='chat_conversations',
    )
    last_message_at = models.DateTimeField(null=True, blank=True)
    first_agent_response_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    disposition = models.CharField(max_length=100, blank=True)
    is_offline_capture = models.BooleanField(default=False)
    satisfaction_rating = models.PositiveSmallIntegerField(null=True, blank=True)
    satisfaction_comment = models.CharField(max_length=500, blank=True)
    satisfaction_submitted_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-last_message_at', '-created_at']


class ChatOperatingHour(models.Model):
    WEEKDAYS = [
        (0, 'Monday'), (1, 'Tuesday'), (2, 'Wednesday'), (3, 'Thursday'),
        (4, 'Friday'), (5, 'Saturday'), (6, 'Sunday'),
    ]
    weekday = models.PositiveSmallIntegerField(choices=WEEKDAYS, unique=True)
    opens_at = models.TimeField(default='08:00')
    closes_at = models.TimeField(default='22:00')
    is_closed = models.BooleanField(default=False)

    class Meta:
        ordering = ['weekday']

    def clean(self):
        if not self.is_closed and self.opens_at >= self.closes_at:
            raise ValidationError('Chat opening time must be before closing time.')


class ChatCannedReply(models.Model):
    STATUS_CHOICES = [('draft', 'Draft'), ('approved', 'Approved'), ('retired', 'Retired')]
    title = models.CharField(max_length=120)
    category = models.CharField(max_length=50, default='general')
    body = models.TextField(max_length=2000)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    approved_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='approved_chat_replies',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    use_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['category', 'title']

    def clean(self):
        if self.status == 'approved' and not self.approved_by_id:
            raise ValidationError('Approved canned replies require an approver.')

    def __str__(self):
        return self.title


class ChatMessage(models.Model):
    SENDER_CHOICES = [
        ('visitor', 'Visitor'), ('guest', 'Guest'), ('agent', 'Agent'),
        ('system', 'System'), ('internal', 'Internal Note'),
    ]
    conversation = models.ForeignKey(ChatConversation, on_delete=models.PROTECT, related_name='messages')
    sender = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='chat_messages',
    )
    sender_type = models.CharField(max_length=20, choices=SENDER_CHOICES)
    body = models.TextField()
    client_message_id = models.UUIDField(null=True, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']
        constraints = [
            models.UniqueConstraint(
                fields=['conversation', 'client_message_id'],
                condition=models.Q(client_message_id__isnull=False),
                name='unique_chat_client_message',
            )
        ]


class ChatStatusHistory(models.Model):
    conversation = models.ForeignKey(ChatConversation, on_delete=models.PROTECT, related_name='history')
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    action = models.CharField(max_length=30)
    actor = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='chat_status_changes',
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']


class ScheduledJob(models.Model):
    HANDLER_CHOICES = [
        ('email_outbox', 'Email outbox'),
        ('brevo_contact_sync', 'Brevo contact synchronization'),
        ('expire_inventory_holds', 'Expire inventory holds'),
        ('manager_pack', 'Generate daily manager pack'),
        ('domain_alerts', 'Evaluate operational alert rules'),
    ]
    key = models.SlugField(max_length=80, unique=True)
    handler = models.CharField(max_length=50, choices=HANDLER_CHOICES)
    interval_minutes = models.PositiveIntegerField(default=5)
    is_enabled = models.BooleanField(default=True)
    next_run_at = models.DateTimeField(db_index=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    consecutive_failures = models.PositiveIntegerField(default=0)
    max_failures = models.PositiveIntegerField(default=5)
    last_error = models.CharField(max_length=500, blank=True)
    locked_at = models.DateTimeField(null=True, blank=True)
    locked_by = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['next_run_at', 'key']

    def __str__(self):
        return self.key


class JobExecution(models.Model):
    STATUS_CHOICES = [('running', 'Running'), ('succeeded', 'Succeeded'), ('failed', 'Failed')]
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    job = models.ForeignKey(ScheduledJob, on_delete=models.PROTECT, related_name='executions')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='running')
    worker_id = models.CharField(max_length=100)
    result = models.JSONField(default=dict, blank=True)
    error = models.CharField(max_length=500, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-started_at']
