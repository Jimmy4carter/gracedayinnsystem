from django.db import models


class HousekeepingTask(models.Model):
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('in_progress', 'In Progress'),
        ('completed', 'Completed'),
        ('verified', 'Verified'),
    ]
    TASK_TYPE_CHOICES = [
        ('cleaning', 'Room Cleaning'),
        ('turndown', 'Turndown Service'),
        ('deep_clean', 'Deep Cleaning'),
        ('maintenance', 'Maintenance Check'),
        ('inspection', 'Inspection'),
        ('other', 'Other'),
    ]

    room = models.ForeignKey('rooms.Room', on_delete=models.PROTECT,
                             related_name='housekeeping_tasks')
    task_type = models.CharField(max_length=20, choices=TASK_TYPE_CHOICES, default='cleaning')
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES, default='medium')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    assigned_to = models.ForeignKey('accounts.UserProfile', on_delete=models.SET_NULL,
                                    null=True, blank=True, related_name='assigned_tasks')
    notes = models.TextField(blank=True)
    scheduled_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey('accounts.UserProfile', on_delete=models.SET_NULL,
                                   null=True, blank=True, related_name='created_tasks')

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_task_type_display()} - Room {self.room.number}'
