from decimal import Decimal

from django.db import models
from django.utils import timezone
import uuid
from django.core.exceptions import ValidationError
from django.db.models import Sum


def generate_invoice_number():
    year = timezone.now().year
    return f'INV-{year}-{uuid.uuid4().hex[:12].upper()}'


def generate_receipt_number():
    year = timezone.now().year
    return f'RCP-{year}-{uuid.uuid4().hex[:12].upper()}'


class Invoice(models.Model):
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('sent', 'Sent'),
        ('paid', 'Paid'),
        ('partially_paid', 'Partially Paid'),
        ('overdue', 'Overdue'),
        ('cancelled', 'Cancelled'),
    ]

    invoice_number = models.CharField(max_length=25, unique=True, blank=True)
    reservation = models.OneToOneField('reservations.Reservation', on_delete=models.PROTECT,
                                       related_name='invoice')
    guest = models.ForeignKey('accounts.UserProfile', on_delete=models.PROTECT,
                              related_name='invoices')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=10)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    due_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.invoice_number}'

    def delete(self, *args, **kwargs):
        raise ValidationError('Invoice records cannot be deleted.')

    def save(self, *args, **kwargs):
        if not self.invoice_number:
            self.invoice_number = generate_invoice_number()
        self.recalculate()
        super().save(*args, **kwargs)

    def recalculate(self):
        items = self.items.all() if self.pk else []
        self.subtotal = sum((item.total for item in items), Decimal('0.00'))
        tax_rate = Decimal(str(self.tax_rate or 0))
        self.tax_amount = (self.subtotal * tax_rate / Decimal('100')).quantize(Decimal('0.01'))
        self.total = self.subtotal + self.tax_amount
        self.balance = self.total - self.amount_paid


class InvoiceItem(models.Model):
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='items')
    description = models.CharField(max_length=255)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    def save(self, *args, **kwargs):
        self.total = self.quantity * self.unit_price
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.description} x{self.quantity}'


class Receipt(models.Model):
    receipt_number = models.CharField(max_length=25, unique=True, blank=True)
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name='receipts')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    issued_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def delete(self, *args, **kwargs):
        raise ValidationError('Receipt records cannot be deleted.')

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            self.receipt_number = generate_receipt_number()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.receipt_number}'


class Folio(models.Model):
    STATUS_CHOICES = [('open', 'Open'), ('closed', 'Closed'), ('void', 'Void')]

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    reservation = models.OneToOneField(
        'reservations.Reservation', on_delete=models.PROTECT, related_name='folio'
    )
    guest = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.PROTECT, related_name='folios'
    )
    currency = models.CharField(max_length=3, default='NGN')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    closed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def delete(self, *args, **kwargs):
        raise ValidationError('Folio records cannot be deleted.')

    class Meta:
        ordering = ['-created_at']

    @property
    def debit_total(self):
        return self.entries.filter(direction='debit').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    @property
    def credit_total(self):
        return self.entries.filter(direction='credit').aggregate(total=Sum('amount'))['total'] or Decimal('0.00')

    @property
    def balance(self):
        return self.debit_total - self.credit_total


class FolioEntry(models.Model):
    DIRECTION_CHOICES = [('debit', 'Debit'), ('credit', 'Credit')]
    ENTRY_TYPE_CHOICES = [
        ('accommodation', 'Accommodation'), ('tax', 'Tax/Fee'),
        ('service', 'Service'), ('payment', 'Payment'), ('refund', 'Refund'),
        ('adjustment', 'Adjustment'), ('credit_note', 'Credit Note'),
    ]

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    folio = models.ForeignKey(Folio, on_delete=models.PROTECT, related_name='entries')
    direction = models.CharField(max_length=10, choices=DIRECTION_CHOICES)
    entry_type = models.CharField(max_length=30, choices=ENTRY_TYPE_CHOICES)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    external_key = models.CharField(max_length=120, unique=True, null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    posted_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='posted_folio_entries',
    )
    posted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['posted_at', 'id']

    def save(self, *args, **kwargs):
        if self.pk and self.__class__.objects.filter(pk=self.pk).exists():
            raise ValidationError('Folio entries are immutable; post a compensating entry instead.')
        self.amount = Decimal(str(self.amount))
        if self.amount <= 0:
            raise ValidationError('Folio entry amount must be greater than zero.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Folio entries cannot be deleted; post a compensating entry instead.')


class FinancialCorrection(models.Model):
    KIND_CHOICES = [('adjustment', 'Debit Adjustment'), ('credit_note', 'Credit Note')]

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    folio = models.ForeignKey(Folio, on_delete=models.PROTECT, related_name='financial_corrections')
    entry = models.OneToOneField(FolioEntry, on_delete=models.PROTECT, related_name='correction')
    kind = models.CharField(max_length=20, choices=KIND_CHOICES)
    reason = models.CharField(max_length=255)
    requested_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.PROTECT, related_name='requested_financial_corrections'
    )
    authorized_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.PROTECT, related_name='authorized_financial_corrections'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        if self.pk and self.__class__.objects.filter(pk=self.pk).exists():
            raise ValidationError('Financial correction records are immutable.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Financial correction records cannot be deleted.')


class FinancialAuditRun(models.Model):
    """Immutable, period-scoped finance control pack prepared by accounting."""
    RUN_TYPES = [('daily', 'Daily close'), ('weekly', 'Weekly review'), ('manual', 'Manual review')]
    STATUS_CHOICES = [('prepared', 'Prepared'), ('approved', 'Approved'), ('rejected', 'Rejected')]

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    period_start = models.DateField()
    period_end = models.DateField()
    run_type = models.CharField(max_length=12, choices=RUN_TYPES, default='daily')
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='prepared')
    metrics = models.JSONField(default=dict)
    exceptions = models.JSONField(default=list)
    source_hash = models.CharField(max_length=64)
    prepared_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.PROTECT, related_name='prepared_financial_audits'
    )
    approved_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.PROTECT, null=True, blank=True,
        related_name='approved_financial_audits'
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    reviewer_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-period_end', '-created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(period_end__gte=models.F('period_start')),
                name='financial_audit_period_valid',
            ),
            models.UniqueConstraint(
                fields=['period_start', 'period_end', 'run_type'],
                name='financial_audit_period_type_unique',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk and self.__class__.objects.filter(pk=self.pk).exists():
            raise ValidationError('Financial audit runs are immutable; create a review event instead.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Financial audit runs cannot be deleted.')


class LedgerAccount(models.Model):
    ACCOUNT_TYPES = [('asset', 'Asset'), ('liability', 'Liability'), ('equity', 'Equity'), ('revenue', 'Revenue'), ('expense', 'Expense')]
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=160)
    account_type = models.CharField(max_length=12, choices=ACCOUNT_TYPES)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f'{self.code} — {self.name}'


class JournalEntry(models.Model):
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    business_date = models.DateField()
    source_type = models.CharField(max_length=80)
    source_id = models.CharField(max_length=80)
    description = models.CharField(max_length=255)
    posted_by = models.ForeignKey('accounts.UserProfile', on_delete=models.PROTECT, null=True, blank=True)
    posted_at = models.DateTimeField(auto_now_add=True)
    external_key = models.CharField(max_length=160, unique=True)

    class Meta:
        ordering = ['-business_date', '-posted_at']

    @property
    def total_debits(self):
        return self.lines.aggregate(total=Sum('debit'))['total'] or Decimal('0.00')

    @property
    def total_credits(self):
        return self.lines.aggregate(total=Sum('credit'))['total'] or Decimal('0.00')

    def save(self, *args, **kwargs):
        if self.pk and self.__class__.objects.filter(pk=self.pk).exists():
            raise ValidationError('Journal entries are immutable.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Journal entries cannot be deleted.')


class JournalLine(models.Model):
    journal = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, related_name='lines')
    account = models.ForeignKey(LedgerAccount, on_delete=models.PROTECT, related_name='journal_lines')
    debit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    credit = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    memo = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [models.CheckConstraint(condition=(models.Q(debit__gt=0) & models.Q(credit=0)) | (models.Q(credit__gt=0) & models.Q(debit=0)), name='journal_line_one_side')]

    def save(self, *args, **kwargs):
        if self.pk and self.__class__.objects.filter(pk=self.pk).exists():
            raise ValidationError('Journal lines are immutable.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Journal lines cannot be deleted.')


class BankAccount(models.Model):
    name = models.CharField(max_length=120)
    bank_name = models.CharField(max_length=120)
    account_last_four = models.CharField(max_length=4)
    ledger_account = models.OneToOneField(LedgerAccount, on_delete=models.PROTECT, related_name='bank_account')
    is_active = models.BooleanField(default=True)


class BankStatementLine(models.Model):
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name='statement_lines')
    statement_date = models.DateField()
    external_reference = models.CharField(max_length=160)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    description = models.CharField(max_length=255, blank=True)
    matched_journal = models.ForeignKey(JournalEntry, on_delete=models.PROTECT, null=True, blank=True, related_name='bank_lines')
    imported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['bank_account', 'external_reference'], name='bank_statement_reference_unique')]


class BankReconciliation(models.Model):
    STATUS_CHOICES = [('open', 'Open'), ('balanced', 'Balanced'), ('exception', 'Exception')]
    bank_account = models.ForeignKey(BankAccount, on_delete=models.PROTECT, related_name='reconciliations')
    period_start = models.DateField()
    period_end = models.DateField()
    statement_balance = models.DecimalField(max_digits=14, decimal_places=2)
    ledger_balance = models.DecimalField(max_digits=14, decimal_places=2)
    difference = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='open')
    prepared_by = models.ForeignKey('accounts.UserProfile', on_delete=models.PROTECT, related_name='prepared_bank_reconciliations')
    reviewed_by = models.ForeignKey('accounts.UserProfile', on_delete=models.PROTECT, null=True, blank=True, related_name='reviewed_bank_reconciliations')
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)


class TaxLiability(models.Model):
    tax_code = models.CharField(max_length=40)
    period_start = models.DateField()
    period_end = models.DateField()
    taxable_amount = models.DecimalField(max_digits=14, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2)
    status = models.CharField(max_length=12, choices=[('open', 'Open'), ('filed', 'Filed'), ('paid', 'Paid')], default='open')
    journal = models.OneToOneField(JournalEntry, on_delete=models.PROTECT, null=True, blank=True)
    prepared_by = models.ForeignKey('accounts.UserProfile', on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)
