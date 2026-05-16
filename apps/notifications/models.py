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
