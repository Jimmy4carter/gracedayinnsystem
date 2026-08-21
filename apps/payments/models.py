import hashlib
import uuid
from django.db import models
from django.core.exceptions import ValidationError


def generate_payment_reference():
    return f'PAY-{uuid.uuid4().hex[:12].upper()}'


class Payment(models.Model):
    METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('bank_transfer', 'Bank Transfer'),
        ('pos', 'POS Terminal'),
        ('online', 'Online Gateway'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]

    reference = models.CharField(max_length=50, unique=True, blank=True)
    invoice = models.ForeignKey('billing.Invoice', on_delete=models.PROTECT,
                                related_name='payments')
    receipt = models.OneToOneField('billing.Receipt', on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='payment_record')
    folio = models.ForeignKey('billing.Folio', on_delete=models.PROTECT, related_name='payments', null=True, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='cash')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    transaction_id = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    processed_by = models.ForeignKey('accounts.UserProfile', on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='processed_payments')
    cashier_shift = models.ForeignKey(
        'payments.CashierShift', on_delete=models.PROTECT, related_name='payments',
        null=True, blank=True,
    )
    idempotency_key = models.CharField(max_length=120, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reference} - {self.amount}'

    def delete(self, *args, **kwargs):
        raise ValidationError('Payment records cannot be deleted.')

    def save(self, *args, **kwargs):
        if not self.reference:
            self.reference = generate_payment_reference()
        super().save(*args, **kwargs)
        if self.status == 'completed':
            self._update_invoice()

    def _update_invoice(self):
        invoice = self.invoice
        completed_payments = invoice.payments.filter(status='completed')
        invoice.amount_paid = sum(p.amount for p in completed_payments)
        invoice.balance = invoice.total - invoice.amount_paid
        if invoice.balance <= 0:
            invoice.status = 'paid'
        elif invoice.amount_paid > 0:
            invoice.status = 'partially_paid'
        Invoice = invoice.__class__
        Invoice.objects.filter(pk=invoice.pk).update(
            amount_paid=invoice.amount_paid,
            balance=invoice.balance,
            status=invoice.status,
        )


class PaymentStatusEvent(models.Model):
    """Append-only payment lifecycle evidence; never update or delete events."""
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name='status_events')
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    actor = models.ForeignKey('accounts.UserProfile', on_delete=models.PROTECT, null=True, blank=True)
    reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def save(self, *args, **kwargs):
        if self.pk and self.__class__.objects.filter(pk=self.pk).exists():
            raise ValidationError('Payment status events are immutable.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Payment status events cannot be deleted.')


class CashierTerminal(models.Model):
    WIDTH_CHOICES = [(58, '58 mm'), (80, '80 mm')]

    code = models.SlugField(max_length=50, unique=True)
    name = models.CharField(max_length=120)
    location = models.CharField(max_length=120, blank=True)
    receipt_width_mm = models.PositiveSmallIntegerField(choices=WIDTH_CHOICES, default=80)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class CashierShift(models.Model):
    STATUS_CHOICES = [('open', 'Open'), ('closed', 'Closed'), ('approved', 'Approved')]

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    terminal = models.ForeignKey(CashierTerminal, on_delete=models.PROTECT, related_name='shifts')
    cashier = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.PROTECT, related_name='cashier_shifts'
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    opening_float = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    expected_cash = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    counted_cash = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    variance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    note = models.TextField(blank=True)
    opened_at = models.DateTimeField(auto_now_add=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    approved_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.PROTECT, null=True, blank=True,
        related_name='approved_cashier_shifts'
    )
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-opened_at']

    def __str__(self):
        return f'{self.terminal.name} - {self.cashier.username} ({self.status})'


class CashMovement(models.Model):
    KIND_CHOICES = [
        ('opening_float', 'Opening Float'),
        ('sale', 'Cash Sale'),
        ('refund', 'Cash Refund'),
        ('paid_in', 'Paid In'),
        ('paid_out', 'Paid Out'),
    ]

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    shift = models.ForeignKey(CashierShift, on_delete=models.PROTECT, related_name='cash_movements')
    movement_type = models.CharField(max_length=20, choices=KIND_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    notes = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.PROTECT, related_name='cash_movements'
    )
    external_key = models.CharField(max_length=120, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def save(self, *args, **kwargs):
        if self.pk and self.__class__.objects.filter(pk=self.pk).exists():
            raise ValidationError('Cash movements are immutable.')
        if self.amount <= 0:
            raise ValidationError('Cash movement amount must be greater than zero.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Cash movements cannot be deleted.')


class PaymentRefund(models.Model):
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name='refunds')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField()
    processed_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.PROTECT, related_name='processed_refunds'
    )
    cashier_shift = models.ForeignKey(
        CashierShift, on_delete=models.PROTECT, related_name='refunds', null=True, blank=True
    )
    idempotency_key = models.CharField(max_length=120, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def save(self, *args, **kwargs):
        if self.pk and self.__class__.objects.filter(pk=self.pk).exists():
            raise ValidationError('Refund records are immutable.')
        if self.amount <= 0:
            raise ValidationError('Refund amount must be greater than zero.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Refund records cannot be deleted.')


class ReceiptPrintJob(models.Model):
    STATUS_CHOICES = [('pending', 'Pending'), ('printed', 'Printed'), ('failed', 'Failed')]

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    receipt = models.ForeignKey('billing.Receipt', on_delete=models.PROTECT, related_name='print_jobs')
    terminal = models.ForeignKey(CashierTerminal, on_delete=models.PROTECT, related_name='print_jobs')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    copy_number = models.PositiveIntegerField(default=1)
    error_message = models.CharField(max_length=255, blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    requested_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.PROTECT, related_name='receipt_print_jobs'
    )
    attempt_count = models.PositiveIntegerField(default=0)
    completed_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='completed_receipt_print_jobs'
    )
    last_attempt_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-requested_at']

    def __str__(self):
        return f'{self.receipt.receipt_number} - {self.status}'
