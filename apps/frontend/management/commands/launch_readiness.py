import json
import os
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.accounts.default_users import DEFAULT_USERS
from apps.accounts.models import GuestProfile, UserProfile
from apps.billing.models import ExpenseCategory, LedgerAccount
from apps.frontend.models import OperationalSetting
from apps.frontend.reconciliation import reconcile_system
from apps.notifications.models import ScheduledJob
from apps.payments.models import CashierTerminal


EXPECTED_JOB_HANDLERS = {
    'email_outbox', 'brevo_contact_sync', 'expire_inventory_holds',
    'manager_pack', 'domain_alerts',
}


class Command(BaseCommand):
    help = 'Verify the database, accounts, storage, email, scheduler, and ledger launch gates.'

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', dest='as_json')
        parser.add_argument(
            '--allow-non-production', action='store_true',
            help='Allow SQLite/DEBUG for local verification while retaining all other gates.',
        )
        parser.add_argument(
            '--prepare-storage', action='store_true',
            help='Create configured static and media roots before verifying them.',
        )

    def handle(self, *args, **options):
        if options['prepare_storage']:
            Path(settings.STATIC_ROOT).mkdir(parents=True, exist_ok=True)
            Path(settings.MEDIA_ROOT).mkdir(parents=True, exist_ok=True)

        checks = {}
        errors = []

        database = settings.DATABASES['default']
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
            server_version = connection.get_database_version()
            sql_mode = ''
            if connection.vendor == 'mysql':
                cursor.execute('SELECT @@sql_mode')
                sql_mode = cursor.fetchone()[0] or ''
        checks['database'] = {
            'vendor': connection.vendor,
            'server_version': '.'.join(str(item) for item in server_version),
            'connection_health_checks': bool(database.get('CONN_HEALTH_CHECKS')),
            'sql_mode': sql_mode,
        }
        if not options['allow_non_production']:
            if settings.DEBUG:
                errors.append('DEBUG must be False.')
            if connection.vendor != 'mysql':
                errors.append('Launch database must be MySQL/MariaDB.')
            if 'STRICT_TRANS_TABLES' not in sql_mode and 'STRICT_ALL_TABLES' not in sql_mode:
                errors.append('MySQL/MariaDB strict SQL mode is required.')

        account_rows = []
        for definition in DEFAULT_USERS:
            user = UserProfile.objects.filter(username=definition['username']).first()
            row = {
                'username': definition['username'], 'email': definition['email'],
                'role': definition['role'], 'exists': bool(user),
            }
            if user:
                row.update({
                    'active': user.is_active,
                    'usable_password': user.has_usable_password(),
                    'attributes_match': (
                        user.email.lower() == definition['email'].lower()
                        and user.role == definition['role']
                        and user.is_staff == (definition['role'] != 'guest')
                        and user.is_superuser == definition.get('superuser', False)
                    ),
                })
                if definition['role'] == 'guest':
                    row['guest_profile'] = GuestProfile.objects.filter(user=user).exists()
            account_rows.append(row)
            if not all((
                row.get('exists'), row.get('active'), row.get('usable_password'),
                row.get('attributes_match'), row.get('guest_profile', True),
            )):
                errors.append(f"Default account is not ready: {definition['username']}.")
        checks['default_accounts'] = account_rows

        required_ledger_codes = {
            '1010', '1020', '1100', '1150', '2100', '4000', '4100', '4200', '5100',
            '5200', '5210', '5220', '5230', '5240', '5250', '5290',
        }
        active_ledger_codes = set(
            LedgerAccount.objects.filter(is_active=True).values_list('code', flat=True)
        )
        missing_ledger_codes = sorted(required_ledger_codes - active_ledger_codes)
        active_expense_categories = ExpenseCategory.objects.filter(is_active=True).count()
        active_terminals = CashierTerminal.objects.filter(is_active=True).count()
        checks['operational_foundation'] = {
            'missing_ledger_codes': missing_ledger_codes,
            'active_expense_categories': active_expense_categories,
            'active_cashier_terminals': active_terminals,
        }
        if missing_ledger_codes:
            errors.append('Required chart-of-accounts entries are missing.')
        if active_expense_categories < 7:
            errors.append('Required expenditure categories are missing.')
        if not active_terminals:
            errors.append('At least one active cashier terminal is required.')

        whatsapp_setting = OperationalSetting.objects.filter(key='whatsapp-contact').first()
        whatsapp_value = whatsapp_setting.value if whatsapp_setting and isinstance(whatsapp_setting.value, dict) else {}
        whatsapp_number = whatsapp_value.get('number') or getattr(settings, 'WHATSAPP_NUMBER', '')
        whatsapp_digits = ''.join(character for character in str(whatsapp_number) if character.isdigit())
        checks['whatsapp'] = {'configured': 8 <= len(whatsapp_digits) <= 15}
        if not checks['whatsapp']['configured']:
            errors.append('Public WhatsApp contact is not configured.')

        cache_key = 'launch-readiness-probe'
        cache_value = os.urandom(12).hex()
        cache.set(cache_key, cache_value, 30)
        cache_ok = cache.get(cache_key) == cache_value
        cache.delete(cache_key)
        checks['cache'] = {'read_write': cache_ok}
        if not cache_ok:
            errors.append('Cache read/write probe failed.')

        enabled_handlers = set(
            ScheduledJob.objects.filter(is_enabled=True).values_list('handler', flat=True)
        )
        missing_handlers = sorted(EXPECTED_JOB_HANDLERS - enabled_handlers)
        failed_jobs = list(
            ScheduledJob.objects.filter(consecutive_failures__gt=0).values(
                'key', 'consecutive_failures', 'last_error'
            )
        )
        checks['scheduler'] = {
            'enabled_handlers': sorted(enabled_handlers),
            'missing_handlers': missing_handlers,
            'failed_jobs': failed_jobs,
        }
        if missing_handlers:
            errors.append('Required scheduled jobs are missing or disabled.')
        if failed_jobs:
            errors.append('One or more scheduled jobs have unresolved failures.')

        email_provider = settings.EMAIL_DELIVERY_PROVIDER.strip().lower()
        email_ready = (
            email_provider == 'brevo' and bool(settings.BREVO_API_KEY)
        ) or (
            email_provider == 'brevo_smtp'
            and bool(
                settings.BREVO_API_KEY
                and settings.EMAIL_HOST_USER
                and settings.EMAIL_HOST_PASSWORD
            )
        )
        checks['email'] = {
            'provider': email_provider,
            'configured': email_ready,
            'sender': settings.DEFAULT_FROM_EMAIL,
        }
        if not email_ready:
            errors.append('Brevo transactional email is not configured.')

        storage_checks = {}
        for name, value in {'static': settings.STATIC_ROOT, 'media': settings.MEDIA_ROOT}.items():
            path = Path(value)
            ready = path.is_dir() and os.access(path, os.W_OK)
            storage_checks[name] = {'path': str(path), 'exists_and_writable': ready}
            if not ready:
                errors.append(f'{name.title()} storage is missing or not writable.')
        checks['storage'] = storage_checks

        reconciliation = reconcile_system()
        checks['reconciliation'] = {
            'ok': reconciliation['ok'],
            'issues': {key: value for key, value in reconciliation['issues'].items() if value},
            'audit_events_checked': reconciliation['audit']['events_checked'],
        }
        if not reconciliation['ok']:
            errors.append('System reconciliation found blocking data integrity issues.')

        result = {'ok': not errors, 'errors': errors, 'checks': checks}
        if options['as_json']:
            self.stdout.write(json.dumps(result, sort_keys=True, default=str))
        else:
            self.stdout.write(
                f"Database={connection.vendor}; accounts={len(account_rows)}; "
                f"scheduler_handlers={len(enabled_handlers)}; reconciliation={reconciliation['ok']}."
            )
            for error in errors:
                self.stderr.write(self.style.ERROR(error))
        if errors:
            raise CommandError(f'Launch readiness failed with {len(errors)} blocking issue(s).')
        self.stdout.write(self.style.SUCCESS('Launch readiness passed.'))
