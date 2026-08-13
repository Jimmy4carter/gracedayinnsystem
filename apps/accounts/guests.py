from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.billing.models import Folio, Invoice
from apps.notifications.models import ChatConversation, InquiryCase, Notification
from apps.reservations.models import (
    BookingQuote, GuestConsentHistory, Reservation, WaitlistEntry,
)
from apps.services.models import ServiceOrder

from .models import GuestMergeHistory, GuestProfile, UserProfile


def duplicate_guest_groups():
    guests = UserProfile.objects.filter(role='guest', merged_into__isnull=True)
    duplicate_emails = guests.exclude(normalized_email='').values('normalized_email').annotate(
        total=Count('id')
    ).filter(total__gt=1).values_list('normalized_email', flat=True)
    duplicate_phones = guests.exclude(normalized_phone='').values('normalized_phone').annotate(
        total=Count('id')
    ).filter(total__gt=1).values_list('normalized_phone', flat=True)
    return guests.filter(
        Q(normalized_email__in=duplicate_emails) | Q(normalized_phone__in=duplicate_phones)
    ).order_by('normalized_email', 'normalized_phone', 'id')


@transaction.atomic
def merge_guest_accounts(*, primary_id, duplicate_id, actor, reason):
    if primary_id == duplicate_id:
        raise ValidationError('Primary and duplicate guests must be different accounts.')
    if not (actor.is_superuser or actor.role in {'admin', 'manager'}):
        raise ValidationError('Only managers or administrators can merge guest accounts.')
    locked = list(UserProfile.objects.select_for_update().filter(
        id__in=[primary_id, duplicate_id]
    ).order_by('id'))
    if len(locked) != 2:
        raise ValidationError('One or both guest accounts were not found.')
    by_id = {item.id: item for item in locked}
    primary, duplicate = by_id[primary_id], by_id[duplicate_id]
    if primary.role != 'guest' or duplicate.role != 'guest':
        raise ValidationError('Only guest accounts can be merged.')
    if primary.merged_into_id or duplicate.merged_into_id:
        raise ValidationError('A previously merged account cannot be merged again.')
    if not reason.strip():
        raise ValidationError('A merge reason is required.')

    snapshot = {
        'id': duplicate.id, 'username': duplicate.username,
        'email': duplicate.email, 'phone': duplicate.phone,
        'first_name': duplicate.first_name, 'last_name': duplicate.last_name,
        'date_joined': duplicate.date_joined.isoformat(),
    }
    transfers = {}
    for name, model, field in [
        ('reservations', Reservation, 'guest'), ('booking_quotes', BookingQuote, 'guest'),
        ('waitlist_entries', WaitlistEntry, 'guest'), ('invoices', Invoice, 'guest'),
        ('folios', Folio, 'guest'), ('service_orders', ServiceOrder, 'guest'),
        ('notifications', Notification, 'recipient'), ('inquiries', InquiryCase, 'requester'),
        ('chat_conversations', ChatConversation, 'guest'),
        ('consent_history', GuestConsentHistory, 'guest'),
    ]:
        queryset = model.objects.filter(**{field: duplicate})
        transfers[name] = queryset.count()
        queryset.update(**{field: primary})

    primary_profile, _ = GuestProfile.objects.get_or_create(user=primary)
    duplicate_profile = GuestProfile.objects.filter(user=duplicate).first()
    if duplicate_profile:
        primary_profile.total_stays += duplicate_profile.total_stays
        primary_profile.total_spent += duplicate_profile.total_spent
        primary_profile.preferences = '\n'.join(filter(None, [primary_profile.preferences, duplicate_profile.preferences]))
        primary_profile.notes = '\n'.join(filter(None, [
            primary_profile.notes,
            f'Merged from {duplicate.username}: {duplicate_profile.notes}'.strip(),
        ]))
        primary_profile.save()
        duplicate_profile.delete()

    if not primary.first_name and duplicate.first_name:
        primary.first_name = duplicate.first_name
    if not primary.last_name and duplicate.last_name:
        primary.last_name = duplicate.last_name
    if not primary.phone and duplicate.phone:
        primary.phone = duplicate.phone
    if not primary.address and duplicate.address:
        primary.address = duplicate.address
    primary.save()

    duplicate.is_active = False
    duplicate.email = ''
    duplicate.phone = ''
    duplicate.address = ''
    duplicate.id_type = ''
    duplicate.id_last_four = ''
    duplicate.merged_into = primary
    duplicate.merged_at = timezone.now()
    duplicate.set_unusable_password()
    duplicate.save()
    return GuestMergeHistory.objects.create(
        primary_guest=primary, duplicate_guest=duplicate, reason=reason.strip(),
        source_snapshot=snapshot, transferred_counts=transfers, merged_by=actor,
    )
