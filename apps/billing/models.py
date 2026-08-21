from decimal import Decimal

from django.db import models
from django.utils import timezone
import uuid
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db.models import Sum


def generate_invoice_number():
    year = timezone.now().year
    return f'INV-{year}-{uuid.uuid4().hex[:12].upper()}'


def generate_receipt_number():
    year = timezone.now().year
    return f'RCP-{year}-{uuid.uuid4().hex[:12].upper()}'


def validate_expenditure_evidence_size(value):
    if value.size > 5 * 1024 * 1024:
        raise ValidationError('Evidence files must not exceed 5 MB.')


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
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    vat_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount_locked = models.BooleanField(
        default=False,
        help_text='Preserves the tax values captured in the reservation price snapshot.',
    )
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
        if self._state.adding and not self.tax_amount_locked and not self.tax_rate:
            from .vat import current_vat_rate
            self.tax_rate = current_vat_rate()
        self.recalculate()
        super().save(*args, **kwargs)

    def recalculate(self):
        items = self.items.all() if self.pk else []
        self.subtotal = sum((item.total for item in items), Decimal('0.00'))
        tax_rate = Decimal(str(self.tax_rate or 0))
        if not self.tax_amount_locked:
            self.tax_amount = (self.subtotal * tax_rate / Decimal('100')).quantize(Decimal('0.01'))
            self.vat_amount = self.tax_amount if tax_rate > 0 else Decimal('0.00')
        self.total = self.subtotal + self.tax_amount
        self.balance = self.total - self.amount_paid

    @property
    def displays_vat(self):
        return self.tax_rate > 0 and self.vat_amount > 0


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

    class Meta:
        ordering = ['-period_end', '-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['bank_account', 'period_start', 'period_end'],
                name='bank_reconciliation_account_period_unique',
            ),
        ]


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


class ExpenseCategory(models.Model):
    code = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=120)
    ledger_account = models.OneToOneField(
        LedgerAccount, on_delete=models.PROTECT, related_name='expense_category'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        verbose_name_plural = 'expense categories'

    def clean(self):
        if self.ledger_account_id and self.ledger_account.account_type != 'expense':
            raise ValidationError({'ledger_account': 'Expense categories require an expense ledger account.'})

    def save(self, *args, **kwargs):
        self.code = self.code.strip().lower()
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.code} — {self.name}'


class Expenditure(models.Model):
    STATUS_CHOICES = [
        ('submitted', 'Submitted'), ('approved', 'Approved'), ('rejected', 'Rejected'),
        ('paid', 'Paid'), ('void', 'Void'),
    ]
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'), ('pos', 'POS / card'), ('bank_transfer', 'Bank transfer'),
        ('online', 'Online payment'),
    ]

    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    business_date = models.DateField(default=timezone.localdate, db_index=True)
    category = models.ForeignKey(ExpenseCategory, on_delete=models.PROTECT, related_name='expenditures')
    vendor = models.CharField(max_length=160)
    description = models.TextField(max_length=1000)
    net_amount = models.DecimalField(max_digits=14, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, editable=False)
    payment_method = models.CharField(max_length=20, choices=PAYMENT_METHOD_CHOICES)
    external_reference = models.CharField(max_length=120, blank=True)
    evidence = models.FileField(
        upload_to='private/expenditure-evidence/%Y/%m/', blank=True,
        validators=[
            FileExtensionValidator(allowed_extensions=['pdf', 'jpg', 'jpeg', 'png', 'webp']),
            validate_expenditure_evidence_size,
        ],
    )
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='submitted', db_index=True)
    submitted_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.PROTECT, related_name='submitted_expenditures'
    )
    approved_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.PROTECT, null=True, blank=True,
        related_name='approved_expenditures',
    )
    paid_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.PROTECT, null=True, blank=True,
        related_name='paid_expenditures',
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    journal = models.OneToOneField(
        JournalEntry, on_delete=models.PROTECT, null=True, blank=True,
        related_name='expenditure',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-business_date', '-created_at']

    IMMUTABLE_FIELDS = (
        'business_date', 'category_id', 'vendor', 'description', 'net_amount',
        'tax_amount', 'total_amount', 'payment_method', 'external_reference',
        'submitted_by_id',
    )

    def clean(self):
        if self.net_amount is None or self.net_amount <= 0:
            raise ValidationError({'net_amount': 'Net amount must be greater than zero.'})
        if self.tax_amount is None or self.tax_amount < 0:
            raise ValidationError({'tax_amount': 'Tax amount cannot be negative.'})

    def save(self, *args, **kwargs):
        self.total_amount = Decimal(self.net_amount or 0) + Decimal(self.tax_amount or 0)
        if self.pk:
            existing = self.__class__.objects.filter(pk=self.pk).values(
                *self.IMMUTABLE_FIELDS, 'evidence'
            ).first()
            if existing:
                changed = [
                    field for field in self.IMMUTABLE_FIELDS
                    if getattr(self, field) != existing[field]
                ]
                if (self.evidence.name or '') != (existing['evidence'] or ''):
                    changed.append('evidence')
                if changed:
                    raise ValidationError(
                        f'Posted expenditure fields are immutable: {", ".join(changed)}.'
                    )
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Expenditure records cannot be deleted; use the controlled void action.')

    def __str__(self):
        return f'EXP-{str(self.reference)[:8].upper()} — {self.vendor}'


class ExpenditureStatusEvent(models.Model):
    expenditure = models.ForeignKey(Expenditure, on_delete=models.PROTECT, related_name='status_events')
    from_status = models.CharField(max_length=12, blank=True)
    to_status = models.CharField(max_length=12)
    actor = models.ForeignKey('accounts.UserProfile', on_delete=models.PROTECT)
    note = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def save(self, *args, **kwargs):
        if self.pk and self.__class__.objects.filter(pk=self.pk).exists():
            raise ValidationError('Expenditure status events are append-only.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Expenditure status events cannot be deleted.')


class VATRateChange(models.Model):
    """Append-only VAT control history; the newest row is the current rate."""

    rate = models.DecimalField(max_digits=5, decimal_places=2)
    previous_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    reason = models.CharField(max_length=255)
    changed_by = models.ForeignKey(
        'accounts.UserProfile', on_delete=models.PROTECT, related_name='vat_rate_changes'
    )
    effective_at = models.DateTimeField(default=timezone.now, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-effective_at', '-id']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rate__gte=0) & models.Q(rate__lte=100),
                name='vat_rate_between_zero_and_hundred',
            ),
        ]

    def clean(self):
        if self.rate < 0 or self.rate > 100:
            raise ValidationError({'rate': 'VAT must be between 0 and 100 percent.'})
        if not self.reason.strip():
            raise ValidationError({'reason': 'A reason is required for the audit trail.'})

    def save(self, *args, **kwargs):
        if self.pk and self.__class__.objects.filter(pk=self.pk).exists():
            raise ValidationError('VAT rate changes are append-only.')
        self.full_clean()
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('VAT rate changes cannot be deleted.')

    def __str__(self):
        return f'VAT {self.rate}% from {self.effective_at:%Y-%m-%d %H:%M}'
