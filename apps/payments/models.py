import uuid
from django.db import models
from django.utils import timezone


def generate_payment_reference():
    now = timezone.now()
    return f'PAY-{now.strftime("%Y%m%d")}-{uuid.uuid4().hex[:8].upper()}'


class Payment(models.Model):
    METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('card', 'Credit/Debit Card'),
        ('bank_transfer', 'Bank Transfer'),
        ('mobile_money', 'Mobile Money'),
        ('other', 'Other'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
        ('refunded', 'Refunded'),
    ]

    reference = models.CharField(max_length=30, unique=True, blank=True)
    invoice = models.ForeignKey('billing.Invoice', on_delete=models.PROTECT,
                                related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=METHOD_CHOICES, default='cash')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    transaction_id = models.CharField(max_length=100, blank=True)
    notes = models.TextField(blank=True)
    processed_by = models.ForeignKey('accounts.UserProfile', on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name='processed_payments')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reference} - {self.amount}'

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
