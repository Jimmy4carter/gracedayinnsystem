from django.contrib import admin
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.utils import timezone

from .models import (
    AnalyticsEvent, AuditLog, BillboardContent, FAQItem, FeatureFlag, GuestTestimonial, LocalGuidePlace,
    LocalGuidePlaceTranslation, ManagementPack, NewsletterSubscription, OperationalSetting,
    PolicyDocument, SitePage, SitePageTranslation,
)
from apps.accounts.admin_permissions import HotelAdminPermissionMixin


@admin.register(AuditLog)
class AuditLogAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
	list_display = ('sequence', 'created_at', 'event_type', 'action', 'actor', 'target_model', 'target_id')
	list_filter = ('event_type', 'action', 'created_at')
	search_fields = ('action', 'target_model', 'target_id', 'actor__username')
	readonly_fields = [field.name for field in AuditLog._meta.fields]

	def has_add_permission(self, request):
		return False

	def has_change_permission(self, request, obj=None):
		return False

	def has_delete_permission(self, request, obj=None):
		return False


@admin.register(NewsletterSubscription)
class NewsletterSubscriptionAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
	list_display = ('email', 'is_active', 'created_at')
	list_filter = ('is_active', 'created_at')
	search_fields = ('email',)
	readonly_fields = ('created_at',)


class SitePageTranslationInline(admin.TabularInline):
    model = SitePageTranslation
    extra = 0


@admin.register(SitePage)
class SitePageAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ('path', 'navigation_title', 'is_published', 'published_at', 'updated_at')
    list_filter = ('is_published',)
    search_fields = ('path', 'navigation_title', 'browser_title', 'hero_title')
    readonly_fields = ('published_at', 'updated_at')
    inlines = [SitePageTranslationInline]


@admin.register(PolicyDocument)
class PolicyDocumentAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ('title', 'policy_type', 'version', 'review_status', 'effective_date', 'is_published', 'updated_at')
    list_filter = ('policy_type', 'review_status', 'is_published')
    search_fields = ('title', 'summary', 'body', 'version')
    readonly_fields = ('review_status', 'review_notes', 'reviewed_by', 'reviewed_at', 'approved_hash', 'is_published', 'published_at', 'updated_at')
    actions = ('approve_selected', 'publish_selected', 'withdraw_selected')

    @admin.action(description='Approve selected current policy versions')
    def approve_selected(self, request, queryset):
        from .content import approve_policy
        for policy in queryset:
            try:
                approve_policy(policy_id=policy.id, actor=request.user, notes='Approved through policy administration.')
            except ValidationError as exc:
                self.message_user(request, f'{policy}: {"; ".join(exc.messages)}', level=messages.ERROR)

    @admin.action(description='Publish selected approved policies')
    def publish_selected(self, request, queryset):
        from .content import publish_policy
        for policy in queryset:
            try:
                publish_policy(policy_id=policy.id, actor=request.user)
            except ValidationError as exc:
                self.message_user(request, f'{policy}: {"; ".join(exc.messages)}', level=messages.ERROR)

    @admin.action(description='Withdraw selected policies')
    def withdraw_selected(self, request, queryset):
        from .content import withdraw_policy
        for policy in queryset:
            withdraw_policy(
                policy_id=policy.id, actor=request.user,
                reason='Withdrawn through policy administration pending revision.',
            )


@admin.register(FAQItem)
class FAQItemAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ('question', 'category', 'display_order', 'is_published', 'updated_at')
    list_filter = ('category', 'is_published')
    list_editable = ('display_order', 'is_published')
    search_fields = ('question', 'answer')


class LocalGuideTranslationInline(admin.TabularInline):
    model = LocalGuidePlaceTranslation
    extra = 0


@admin.register(LocalGuidePlace)
class LocalGuidePlaceAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ('name', 'category', 'travel_minutes', 'is_published', 'display_order')
    list_filter = ('category', 'is_published')
    search_fields = ('name', 'summary', 'address')
    inlines = [LocalGuideTranslationInline]


@admin.register(GuestTestimonial)
class GuestTestimonialAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ('display_name', 'rating', 'status', 'publication_consent', 'created_at')
    list_filter = ('status', 'rating', 'publication_consent')
    search_fields = ('display_name', 'body')
    readonly_fields = ('guest', 'reservation', 'display_name', 'rating', 'body',
                       'publication_consent', 'created_at', 'reviewed_at')
    actions = ('approve_testimonials', 'reject_testimonials')

    @admin.action(description='Approve selected testimonials with consent')
    def approve_testimonials(self, request, queryset):
        queryset.filter(publication_consent=True).update(
            status='approved', reviewed_by=request.user, reviewed_at=timezone.now(),
        )

    @admin.action(description='Reject selected testimonials')
    def reject_testimonials(self, request, queryset):
        queryset.update(status='rejected', reviewed_by=request.user, reviewed_at=timezone.now())


@admin.register(FeatureFlag)
class FeatureFlagAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ('key', 'is_enabled', 'roles', 'updated_at')
    list_filter = ('is_enabled',)


@admin.register(OperationalSetting)
class OperationalSettingAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ('key', 'description', 'is_secret', 'updated_at')
    readonly_fields = ('updated_at',)


@admin.register(AnalyticsEvent)
class AnalyticsEventAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ('event_name', 'path', 'user', 'occurred_at')
    list_filter = ('event_name', 'occurred_at')
    readonly_fields = [field.name for field in AnalyticsEvent._meta.fields]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(BillboardContent)
class BillboardContentAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ('title', 'content_type', 'priority', 'layout_variant', 'duration_seconds', 'is_active', 'start_at', 'end_at')
    list_filter = ('content_type', 'priority', 'layout_variant', 'transition_variant', 'is_active')
    list_editable = ('priority', 'duration_seconds', 'is_active')
    search_fields = ('title', 'subtitle', 'body')
    readonly_fields = ('updated_at',)
    fieldsets = (
        ('Programme', {'fields': ('title', 'subtitle', 'body', 'content_type', 'icon')}),
        ('Media', {'fields': ('image', 'video', 'fallback_image')}),
        ('Broadcast rules', {'fields': ('priority', 'layout_variant', 'transition_variant', 'duration_seconds', 'display_order', 'start_at', 'end_at', 'is_active')}),
        ('Call to action', {'fields': ('cta_text', 'cta_url')}),
        ('System', {'fields': ('updated_at',)}),
    )


@admin.register(ManagementPack)
class ManagementPackAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ('business_date', 'generated_by', 'created_at', 'expires_at')
    readonly_fields = [field.name for field in ManagementPack._meta.fields]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


from .models import (
    DailyMetricSnapshot, ManagementQuery, ManagementQueryHistory,
    ManagementQueryNote, MetricDefinition, NewsletterMessage, NightAuditRun,
)


@admin.register(NewsletterMessage)
class NewsletterMessageAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ('subject', 'status', 'recipient', 'created_at')
    list_filter = ('status', 'recipient', 'created_at')
    search_fields = ('subject', 'title', 'message')
    readonly_fields = ('created_at', 'updated_at')


admin.site.register(MetricDefinition)


@admin.register(DailyMetricSnapshot)
class DailyMetricSnapshotAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['business_date', 'occupancy_percent', 'room_revenue', 'adr', 'revpar', 'receivables']
    readonly_fields = [field.name for field in DailyMetricSnapshot._meta.fields]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


@admin.register(NightAuditRun)
class NightAuditRunAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['business_date', 'status', 'completed_by', 'completed_at']
    readonly_fields = [field.name for field in NightAuditRun._meta.fields]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False


class ManagementQueryNoteInline(admin.TabularInline):
    model = ManagementQueryNote
    extra = 0


@admin.register(ManagementQuery)
class ManagementQueryAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['reference', 'title', 'priority', 'status', 'raised_by', 'assigned_to', 'due_at']
    list_filter = ['status', 'priority']
    inlines = [ManagementQueryNoteInline]


@admin.register(ManagementQueryHistory)
class ManagementQueryHistoryAdmin(HotelAdminPermissionMixin, admin.ModelAdmin):
    list_display = ['query', 'action', 'from_status', 'to_status', 'actor', 'created_at']
    readonly_fields = [field.name for field in ManagementQueryHistory._meta.fields]

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False
