from django.contrib import admin
from .models import HousekeepingTask


@admin.register(HousekeepingTask)
class HousekeepingTaskAdmin(admin.ModelAdmin):
    list_display = ['room', 'task_type', 'priority', 'status', 'assigned_to', 'created_at']
    list_filter = ['status', 'priority', 'task_type']
    search_fields = ['room__number']
