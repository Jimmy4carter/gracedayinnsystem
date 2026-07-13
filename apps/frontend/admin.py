from django.contrib import admin

from .models import AuditLog, NewsletterSubscription


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
	list_display = ('created_at', 'event_type', 'action', 'actor', 'target_model', 'target_id')
	list_filter = ('event_type', 'action', 'created_at')
	search_fields = ('action', 'target_model', 'target_id', 'actor__username')
	readonly_fields = ('created_at',)


@admin.register(NewsletterSubscription)
class NewsletterSubscriptionAdmin(admin.ModelAdmin):
	list_display = ('email', 'is_active', 'created_at')
	list_filter = ('is_active', 'created_at')
	search_fields = ('email',)
	readonly_fields = ('created_at',)
