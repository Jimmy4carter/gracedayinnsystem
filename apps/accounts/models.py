from django.contrib.auth.models import AbstractUser
from django.db import models


class UserProfile(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('manager', 'Manager'),
        ('receptionist', 'Receptionist'),
        ('housekeeping', 'Housekeeping'),
        ('guest', 'Guest'),
    ]
    ID_TYPE_CHOICES = [
        ('passport', 'Passport'),
        ('national_id', 'National ID'),
        ('drivers_license', "Driver's License"),
        ('other', 'Other'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='guest')
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    address = models.TextField(blank=True)
    id_type = models.CharField(max_length=20, choices=ID_TYPE_CHOICES, blank=True)
    id_number = models.CharField(max_length=50, blank=True)
    nationality = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return f'{self.username} ({self.get_role_display()})'

    @property
    def is_staff_member(self):
        return self.role in ('admin', 'manager', 'receptionist', 'housekeeping')


class GuestProfile(models.Model):
    user = models.OneToOneField(UserProfile, on_delete=models.CASCADE, related_name='guest_profile')
    date_of_birth = models.DateField(null=True, blank=True)
    preferences = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    total_stays = models.PositiveIntegerField(default=0)
    total_spent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Guest Profile'
        verbose_name_plural = 'Guest Profiles'

    def __str__(self):
        return f'Guest: {self.user.get_full_name() or self.user.username}'
