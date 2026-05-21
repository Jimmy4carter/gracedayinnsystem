from django.contrib import admin

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
	list_display = ('created_at', 'event_type', 'action', 'actor', 'target_model', 'target_id')
	list_filter = ('event_type', 'action', 'created_at')
	search_fields = ('action', 'target_model', 'target_id', 'actor__username')
	readonly_fields = ('created_at',)
