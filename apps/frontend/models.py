from django.db import models


class AuditLog(models.Model):
	EVENT_CHOICES = [
		('reservation', 'Reservation'),
		('payment', 'Payment'),
		('housekeeping', 'Housekeeping'),
		('service', 'Service'),
		('security', 'Security'),
	]

	actor = models.ForeignKey(
		'accounts.UserProfile',
		on_delete=models.SET_NULL,
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
	created_at = models.DateTimeField(auto_now_add=True)

	class Meta:
		ordering = ['-created_at']

	def __str__(self):
		return f'{self.event_type}:{self.action} by {self.actor_id or "system"}'

# Create your models here.

class NewsletterSubscription(models.Model):
    email = models.EmailField(unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.email} (Active: {self.is_active})'
