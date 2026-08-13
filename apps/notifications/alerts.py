from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone

from apps.accounts.models import UserProfile
from apps.housekeeping.models import HousekeepingTask, MaintenanceTicket
from apps.rooms.models import Room

from .models import (
    AlertRule, ChatConversation, InquiryCase, Notification, OperationalAlert,
    OperationalAlertHistory, ScheduledJob,
)


def _room_state_findings(rule, now):
    findings = []
    for room in Room.objects.filter(is_active=True).prefetch_related(
        'reservations', 'housekeeping_tasks', 'maintenance_tickets'
    ):
        occupied = room.reservations.filter(status='checked_in').exists()
        active_housekeeping = room.housekeeping_tasks.filter(
            status__in=['pending', 'in_progress', 'completed']
        ).exists()
        downtime = room.maintenance_tickets.filter(
            downtime_required=True, status__in=['reported', 'in_progress', 'resolved']
        ).exists()
        conditions = []
        if occupied and room.status != 'occupied':
            conditions.append(('checked-in-status', f'Room {room.number} has a checked-in stay but is marked {room.get_status_display()}.'))
        if room.status == 'occupied' and not occupied:
            conditions.append(('occupied-without-stay', f'Room {room.number} is marked occupied without a checked-in stay.'))
        if room.status == 'available' and active_housekeeping:
            conditions.append(('available-with-housekeeping', f'Room {room.number} is available while housekeeping is incomplete or unverified.'))
        if room.status == 'available' and downtime:
            conditions.append(('available-with-downtime', f'Room {room.number} is available while maintenance downtime is open.'))
        for code, detail in conditions:
            findings.append({
                'key': f'{rule.key}:room:{room.id}:{code}', 'title': 'Room-state discrepancy',
                'detail': detail, 'source_model': 'Room', 'source_id': str(room.id),
                'link': '/portal/rooms/',
            })
    return findings


def _overdue_housekeeping_findings(rule, now):
    cutoff = now - timedelta(minutes=rule.threshold_minutes)
    tasks = HousekeepingTask.objects.filter(status__in=['pending', 'in_progress']).filter(
        Q(scheduled_at__lt=cutoff) | Q(scheduled_at__isnull=True, created_at__lt=cutoff)
    ).select_related('room')
    return [{
        'key': f'{rule.key}:task:{item.id}', 'title': 'Overdue housekeeping task',
        'detail': f'{item.get_task_type_display()} for Room {item.room.number} is overdue.',
        'source_model': 'HousekeepingTask', 'source_id': str(item.id),
        'link': '/portal/housekeeping/',
    } for item in tasks]


def _overdue_maintenance_findings(rule, now):
    cutoff = now - timedelta(minutes=rule.threshold_minutes)
    tickets = MaintenanceTicket.objects.filter(
        status__in=['reported', 'in_progress', 'resolved'], updated_at__lt=cutoff,
    ).select_related('room')
    return [{
        'key': f'{rule.key}:ticket:{item.id}', 'title': 'Overdue maintenance ticket',
        'detail': f'{item.title} for Room {item.room.number} has exceeded its response threshold.',
        'source_model': 'MaintenanceTicket', 'source_id': str(item.id),
        'link': '/portal/maintenance/',
    } for item in tickets]


def _unanswered_chat_findings(rule, now):
    cutoff = now - timedelta(minutes=rule.threshold_minutes)
    conversations = ChatConversation.objects.filter(
        status__in=['queued', 'open'], first_agent_response_at__isnull=True,
        created_at__lt=cutoff,
    )
    return [{
        'key': f'{rule.key}:chat:{item.id}', 'title': 'Unanswered live chat',
        'detail': f'Conversation {item.reference} has not received an agent response.',
        'source_model': 'ChatConversation', 'source_id': str(item.id),
        'link': f'/portal/chat/{item.reference}/',
    } for item in conversations]


def _inquiry_sla_findings(rule, now):
    cases = InquiryCase.objects.filter(status__in=['new', 'acknowledged', 'in_progress']).filter(
        Q(first_responded_at__isnull=True, first_response_due_at__lt=now)
        | Q(resolution_due_at__lt=now)
    )
    return [{
        'key': f'{rule.key}:inquiry:{item.id}', 'title': 'Inquiry SLA breach',
        'detail': f'Inquiry {item.reference} ({item.subject}) has exceeded an SLA deadline.',
        'source_model': 'InquiryCase', 'source_id': str(item.id),
        'link': f'/portal/inquiries/{item.id}/',
    } for item in cases]


def _job_failure_findings(rule, now):
    try:
        failure_count = max(1, int(rule.configuration.get('failure_count', 1)))
    except (TypeError, ValueError):
        failure_count = 1
    jobs = ScheduledJob.objects.filter(
        Q(consecutive_failures__gte=failure_count)
        | Q(is_enabled=False, last_error__gt='')
    )
    return [{
        'key': f'{rule.key}:job:{item.id}', 'title': 'Scheduled job failure',
        'detail': f'{item.key} has {item.consecutive_failures} consecutive failures: {item.last_error}',
        'source_model': 'ScheduledJob', 'source_id': str(item.id),
        'link': '/portal/management/',
    } for item in jobs]


EVALUATORS = {
    'room_state': _room_state_findings,
    'overdue_housekeeping': _overdue_housekeeping_findings,
    'overdue_maintenance': _overdue_maintenance_findings,
    'unanswered_chat': _unanswered_chat_findings,
    'inquiry_sla': _inquiry_sla_findings,
    'job_failure': _job_failure_findings,
}


def _notify_recipients(rule, alert):
    roles = rule.recipient_roles or ['admin', 'manager']
    recipients = UserProfile.objects.filter(is_active=True).filter(Q(is_superuser=True) | Q(role__in=roles)).distinct()
    Notification.objects.bulk_create([
        Notification(
            recipient=recipient, title=alert.title, message=alert.detail,
            notification_type='system', link=alert.link,
        ) for recipient in recipients
    ])


@transaction.atomic
def evaluate_alert_rule(rule, *, now=None):
    if not rule.is_enabled:
        return {'opened': 0, 'updated': 0, 'resolved': 0}
    now = now or timezone.now()
    findings = EVALUATORS[rule.rule_type](rule, now)
    observed = {item['key'] for item in findings}
    counts = {'opened': 0, 'updated': 0, 'resolved': 0}
    for finding in findings:
        alert = OperationalAlert.objects.select_for_update().filter(dedupe_key=finding['key']).first()
        if not alert:
            alert = OperationalAlert.objects.create(
                rule=rule, dedupe_key=finding['key'], severity=rule.severity, **{
                    key: value for key, value in finding.items() if key != 'key'
                },
            )
            OperationalAlertHistory.objects.create(
                alert=alert, action='detected', from_status='', to_status='open',
            )
            _notify_recipients(rule, alert)
            counts['opened'] += 1
        else:
            previous = alert.status
            alert.title, alert.detail, alert.severity = finding['title'], finding['detail'], rule.severity
            alert.last_detected_at = now
            alert.occurrence_count = F('occurrence_count') + 1
            if alert.status == 'resolved':
                alert.status, alert.resolved_at, alert.resolved_by, alert.resolution_notes = 'open', None, None, ''
            alert.save()
            alert.refresh_from_db(fields=['occurrence_count', 'status'])
            if previous == 'resolved':
                OperationalAlertHistory.objects.create(
                    alert=alert, action='redetected', from_status='resolved', to_status='open',
                )
                _notify_recipients(rule, alert)
                counts['opened'] += 1
            else:
                counts['updated'] += 1
    stale = OperationalAlert.objects.select_for_update().filter(
        rule=rule, status__in=['open', 'acknowledged'],
    ).exclude(dedupe_key__in=observed)
    for alert in stale:
        previous = alert.status
        alert.status, alert.resolved_at = 'resolved', now
        alert.resolution_notes = 'Condition cleared automatically during rule evaluation.'
        alert.save(update_fields=['status', 'resolved_at', 'resolution_notes'])
        OperationalAlertHistory.objects.create(
            alert=alert, action='auto_resolve', from_status=previous, to_status='resolved',
            notes=alert.resolution_notes,
        )
        counts['resolved'] += 1
    return counts


def evaluate_alert_rules(*, now=None):
    totals = {'rules': 0, 'opened': 0, 'updated': 0, 'resolved': 0}
    for rule in AlertRule.objects.filter(is_enabled=True):
        result = evaluate_alert_rule(rule, now=now)
        totals['rules'] += 1
        for key in ('opened', 'updated', 'resolved'):
            totals[key] += result[key]
    return totals


@transaction.atomic
def transition_alert(*, alert_id, action, actor, notes=''):
    if not (actor.is_superuser or actor.role in {'admin', 'manager'}):
        raise ValidationError('Only management can control operational alerts.')
    alert = OperationalAlert.objects.select_for_update().get(pk=alert_id)
    previous = alert.status
    now = timezone.now()
    if action == 'acknowledge' and previous == 'open':
        alert.status, alert.acknowledged_by, alert.acknowledged_at = 'acknowledged', actor, now
    elif action == 'resolve' and previous in {'open', 'acknowledged'}:
        if not notes.strip():
            raise ValidationError('Resolution notes are required.')
        alert.status, alert.resolved_by, alert.resolved_at = 'resolved', actor, now
        alert.resolution_notes = notes.strip()
    else:
        raise ValidationError('This alert cannot receive that action.')
    alert.save()
    OperationalAlertHistory.objects.create(
        alert=alert, action=action, from_status=previous, to_status=alert.status,
        actor=actor, notes=notes.strip(),
    )
    return alert
