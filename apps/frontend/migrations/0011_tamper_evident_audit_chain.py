import hashlib
import json

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


ZERO_HASH = '0' * 64


def backfill_audit_chain(apps, schema_editor):
    AuditLog = apps.get_model('frontend', 'AuditLog')
    AuditChainHead = apps.get_model('frontend', 'AuditChainHead')
    previous_hash = ZERO_HASH
    sequence = 0
    for item in AuditLog.objects.order_by('created_at', 'id').iterator():
        sequence += 1
        payload = {
            'sequence': sequence, 'previous_hash': previous_hash,
            'actor_id': item.actor_id, 'event_type': item.event_type, 'action': item.action,
            'target_model': item.target_model, 'target_id': item.target_id,
            'details': item.details, 'ip_address': item.ip_address,
            'user_agent': item.user_agent, 'created_at': item.created_at.isoformat(),
        }
        event_hash = hashlib.sha256(json.dumps(
            payload, sort_keys=True, separators=(',', ':'), default=str,
        ).encode('utf-8')).hexdigest()
        AuditLog.objects.filter(pk=item.pk).update(
            sequence=sequence, previous_hash=previous_hash, event_hash=event_hash,
        )
        previous_hash = event_hash
    AuditChainHead.objects.update_or_create(
        pk=1, defaults={'last_sequence': sequence, 'last_hash': previous_hash},
    )


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('frontend', '0010_localguideplace_sitepagetranslation_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='AuditChainHead',
            fields=[
                ('id', models.PositiveSmallIntegerField(default=1, editable=False, primary_key=True, serialize=False)),
                ('last_sequence', models.PositiveBigIntegerField(default=0, editable=False)),
                ('last_hash', models.CharField(default=ZERO_HASH, editable=False, max_length=64)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddField(
            model_name='auditlog', name='sequence',
            field=models.PositiveBigIntegerField(editable=False, null=True, unique=True),
        ),
        migrations.AddField(
            model_name='auditlog', name='previous_hash',
            field=models.CharField(editable=False, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name='auditlog', name='event_hash',
            field=models.CharField(editable=False, max_length=64, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='auditlog', name='actor',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='audit_logs', to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name='auditlog', name='created_at',
            field=models.DateTimeField(default=django.utils.timezone.now, editable=False),
        ),
        migrations.AlterField(
            model_name='auditlog', name='event_type',
            field=models.CharField(choices=[
                ('reservation', 'Reservation'), ('payment', 'Payment'),
                ('housekeeping', 'Housekeeping'), ('service', 'Service'),
                ('security', 'Security'), ('system', 'System'),
            ], max_length=20),
        ),
        migrations.RunPython(backfill_audit_chain, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='auditlog', name='sequence',
            field=models.PositiveBigIntegerField(editable=False, unique=True),
        ),
        migrations.AlterField(
            model_name='auditlog', name='previous_hash',
            field=models.CharField(editable=False, max_length=64),
        ),
        migrations.AlterField(
            model_name='auditlog', name='event_hash',
            field=models.CharField(editable=False, max_length=64, unique=True),
        ),
    ]
