from decimal import Decimal

from django.db import models
from django.utils import timezone


def generate_invoice_number():
    from apps.billing.models import Invoice
    year = timezone.now().year
    count = Invoice.objects.filter(created_at__year=year).count() + 1
    return f'GDI-INV-{year}-{count:04d}'


def generate_receipt_number():
    from apps.billing.models import Receipt
    year = timezone.now().year
    count = Receipt.objects.filter(created_at__year=year).count() + 1
    return f'GDI-RCP-{year}-{count:04d}'


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

    def save(self, *args, **kwargs):
        if not self.receipt_number:
            self.receipt_number = generate_receipt_number()
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.receipt_number}'
