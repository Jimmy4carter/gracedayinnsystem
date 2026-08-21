from django.contrib import admin
from .models import (
    AlertRule, BrevoContactSync, CommunicationTemplate,
    ContactPreference, DeliveryAttempt, DeliveryEvent,
    InquiryAttachment, InquiryCase, InquiryMessage, InquiryRoutingRule, InquiryStatusHistory, JobExecution, Notification,
    OperationalAlert, OperationalAlertHistory, OutboundMessage, ScheduledJob, Suppression,
)
from apps.accounts.admin_permissions import HotelAdminPermissionMixin


@admin.register(Notification)
class NotificationAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['title', 'recipient', 'notification_type', 'is_read', 'created_at']
    list_filter = ['notification_type', 'is_read']


@admin.register(AlertRule)
class AlertRuleAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['key', 'name', 'rule_type', 'severity', 'threshold_minutes', 'is_enabled']
    list_filter = ['rule_type', 'severity', 'is_enabled']

    def get_queryset(self, request):
        return super().get_queryset(request).exclude(rule_type='unanswered_chat')


@admin.register(OperationalAlert)
class OperationalAlertAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['reference', 'title', 'severity', 'status', 'occurrence_count', 'last_detected_at']
    list_filter = ['status', 'severity', 'rule']
    search_fields = ['title', 'detail', 'source_model', 'source_id']
    readonly_fields = [field.name for field in OperationalAlert._meta.fields]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(OperationalAlertHistory)
class OperationalAlertHistoryAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['alert', 'action', 'from_status', 'to_status', 'actor', 'created_at']
    readonly_fields = [field.name for field in OperationalAlertHistory._meta.fields]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(CommunicationTemplate)
class CommunicationTemplateAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['key', 'locale', 'version', 'status', 'subject']
    list_filter = ['status', 'locale']


@admin.register(OutboundMessage)
class OutboundMessageAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['reference', 'purpose', 'recipient_email', 'status', 'provider', 'attempt_count', 'created_at']
    list_filter = ['status', 'provider', 'purpose']
    search_fields = ['recipient_email', 'subject', 'provider_message_id']
    readonly_fields = [field.name for field in OutboundMessage._meta.fields]


@admin.register(DeliveryAttempt)
class DeliveryAttemptAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['message', 'attempt_number', 'outcome', 'response_code', 'created_at']
    readonly_fields = [field.name for field in DeliveryAttempt._meta.fields]


@admin.register(DeliveryEvent)
class DeliveryEventAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['event_type', 'recipient_email', 'provider_message_id', 'occurred_at', 'received_at']
    readonly_fields = [field.name for field in DeliveryEvent._meta.fields]


admin.site.register(ContactPreference)
admin.site.register(Suppression)


@admin.register(BrevoContactSync)
class BrevoContactSyncAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['email', 'status', 'desired_marketing_consent', 'attempt_count', 'last_synced_at']
    list_filter = ['status', 'desired_marketing_consent']
    readonly_fields = [field.name for field in BrevoContactSync._meta.fields]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


class InquiryMessageInline(admin.TabularInline):
    model = InquiryMessage
    extra = 0
    readonly_fields = ['sender', 'sender_name', 'sender_email', 'body', 'is_internal', 'created_at']

    def has_add_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


class InquiryAttachmentInline(admin.TabularInline):
    model = InquiryAttachment
    extra = 0
    readonly_fields = [field.name for field in InquiryAttachment._meta.fields]

    def has_add_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(InquiryCase)
class InquiryCaseAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['reference', 'subject', 'category', 'priority', 'status', 'owner', 'created_at']
    list_filter = ['status', 'category', 'priority']
    search_fields = ['subject', 'requester_name', 'requester_email']
    readonly_fields = ['reference', 'requester', 'requester_name', 'requester_email', 'created_at', 'updated_at']
    inlines = [InquiryMessageInline, InquiryAttachmentInline]


@admin.register(InquiryRoutingRule)
class InquiryRoutingRuleAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['name', 'category', 'source', 'priority', 'owner', 'order', 'is_active']
    list_filter = ['category', 'priority', 'is_active']


@admin.register(InquiryStatusHistory)
class InquiryStatusHistoryAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['case', 'action', 'from_status', 'to_status', 'actor', 'created_at']
    readonly_fields = [field.name for field in InquiryStatusHistory._meta.fields]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(ScheduledJob)
class ScheduledJobAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['key', 'handler', 'is_enabled', 'next_run_at', 'consecutive_failures', 'last_run_at']
    list_filter = ['handler', 'is_enabled']
    readonly_fields = ['last_run_at', 'consecutive_failures', 'last_error', 'locked_at', 'locked_by', 'created_at', 'updated_at']


@admin.register(JobExecution)
class JobExecutionAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['reference', 'job', 'status', 'worker_id', 'started_at', 'finished_at']
    list_filter = ['status', 'job']
    readonly_fields = [field.name for field in JobExecution._meta.fields]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False
