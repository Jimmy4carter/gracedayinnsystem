from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone
import uuid


def normalize_guest_email(value):
    return (value or '').strip().lower()


def normalize_guest_phone(value):
    digits = ''.join(character for character in (value or '') if character.isdigit())
    if len(digits) == 11 and digits.startswith('0'):
        return f'234{digits[1:]}'
    if len(digits) == 10:
        return f'234{digits}'
    return digits


class UserProfile(AbstractUser):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('manager', 'Manager'),
        ('receptionist', 'Receptionist'),
        ('accountant', 'Accountant'),
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
    id_document = models.FileField(upload_to='id_documents/', blank=True, null=True)
    id_type = models.CharField(max_length=20, choices=ID_TYPE_CHOICES, blank=True)
    id_last_four = models.CharField(max_length=4, blank=True)
    nationality = models.CharField(max_length=100, blank=True)
    normalized_email = models.EmailField(blank=True, db_index=True)
    normalized_phone = models.CharField(max_length=20, blank=True, db_index=True)
    merged_into = models.ForeignKey(
        'self', on_delete=models.PROTECT, null=True, blank=True, related_name='merged_guest_accounts'
    )
    merged_at = models.DateTimeField(null=True, blank=True)
    privacy_legal_hold = models.BooleanField(default=False)
    anonymized_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = 'User Profile'
        verbose_name_plural = 'User Profiles'

    def __str__(self):
        return f'{self.username} ({self.get_role_display()})'

    def save(self, *args, **kwargs):
        self.normalized_email = normalize_guest_email(self.email)
        self.normalized_phone = normalize_guest_phone(self.phone)
        if self.id_last_four:
            self.id_last_four = self.id_last_four[-4:]
        if kwargs.get('update_fields') is not None:
            kwargs['update_fields'] = set(kwargs['update_fields']) | {
                'normalized_email', 'normalized_phone', 'id_last_four',
            }
        return super().save(*args, **kwargs)

    @property
    def is_staff_member(self):
        return self.role in ('admin', 'manager', 'receptionist', 'accountant', 'housekeeping')


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


class GuestMergeHistory(models.Model):
    primary_guest = models.ForeignKey(
        UserProfile, on_delete=models.PROTECT, related_name='received_guest_merges'
    )
    duplicate_guest = models.OneToOneField(
        UserProfile, on_delete=models.PROTECT, related_name='guest_merge_record'
    )
    reason = models.CharField(max_length=255)
    source_snapshot = models.JSONField(default=dict)
    transferred_counts = models.JSONField(default=dict)
    merged_by = models.ForeignKey(
        UserProfile, on_delete=models.PROTECT, related_name='performed_guest_merges'
    )
    merged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-merged_at']

    def save(self, *args, **kwargs):
        if self.pk and self.__class__.objects.filter(pk=self.pk).exists():
            from django.core.exceptions import ValidationError
            raise ValidationError('Guest merge history is immutable.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError('Guest merge history cannot be deleted.')


class DataPrivacyRequest(models.Model):
    TYPE_CHOICES = [
        ('export', 'Access / Export'), ('correction', 'Correction'),
        ('anonymize', 'Anonymization'),
    ]
    STATUS_CHOICES = [
        ('submitted', 'Submitted'), ('approved', 'Approved'),
        ('rejected', 'Rejected'), ('completed', 'Completed'),
    ]
    reference = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    guest = models.ForeignKey(UserProfile, on_delete=models.PROTECT, related_name='privacy_requests')
    request_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    details = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='submitted')
    decision_reason = models.CharField(max_length=500, blank=True)
    reviewed_by = models.ForeignKey(
        UserProfile, on_delete=models.PROTECT, null=True, blank=True,
        related_name='reviewed_privacy_requests',
    )
    artifact = models.FileField(upload_to='protected/privacy/%Y/%m/', blank=True)
    artifact_expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']


class DataPrivacyRequestHistory(models.Model):
    request = models.ForeignKey(DataPrivacyRequest, on_delete=models.PROTECT, related_name='history')
    action = models.CharField(max_length=30)
    from_status = models.CharField(max_length=20, blank=True)
    to_status = models.CharField(max_length=20)
    actor = models.ForeignKey(
        UserProfile, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='privacy_request_actions',
    )
    notes = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def save(self, *args, **kwargs):
        if self.pk and self.__class__.objects.filter(pk=self.pk).exists():
            from django.core.exceptions import ValidationError
            raise ValidationError('Privacy request history is immutable.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        from django.core.exceptions import ValidationError
        raise ValidationError('Privacy request history cannot be deleted.')


class StaffMFADevice(models.Model):
    user = models.OneToOneField(
        UserProfile, on_delete=models.PROTECT, related_name='mfa_device',
    )
    encrypted_secret = models.BinaryField(editable=False)
    is_confirmed = models.BooleanField(default=False)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    recovery_code_hashes = models.JSONField(default=list, blank=True)
    last_counter = models.BigIntegerField(default=-1)
    failed_attempts = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Staff MFA device'

    def __str__(self):
        return f'MFA for {self.user.username}'
