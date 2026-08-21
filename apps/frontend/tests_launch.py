import tempfile
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.accounts.default_users import DEFAULT_USERS, ensure_default_users
from apps.accounts.models import UserProfile


class LaunchReadinessTests(TestCase):
    def password_environment(self):
        return {
            item['env']: f"Launch-{item['role']}-Strong-2026!{index}Xq"
            for index, item in enumerate(DEFAULT_USERS, start=1)
        }

    def provision_accounts(self):
        with patch.dict('os.environ', self.password_environment(), clear=False):
            ensure_default_users()

    @override_settings(EMAIL_DELIVERY_PROVIDER='brevo', BREVO_API_KEY='test-only-key')
    def test_local_launch_readiness_covers_accounts_storage_jobs_and_reconciliation(self):
        self.provision_accounts()
        with tempfile.TemporaryDirectory() as directory, override_settings(
            STATIC_ROOT=f'{directory}/static', MEDIA_ROOT=f'{directory}/media',
        ):
            output = StringIO()
            call_command(
                'launch_readiness', allow_non_production=True,
                prepare_storage=True, stdout=output,
            )
        self.assertIn('Launch readiness passed', output.getvalue())

    @override_settings(EMAIL_DELIVERY_PROVIDER='brevo', BREVO_API_KEY='test-only-key')
    def test_missing_default_role_account_blocks_launch(self):
        self.provision_accounts()
        UserProfile.objects.filter(username='accountant').delete()
        with tempfile.TemporaryDirectory() as directory, override_settings(
            STATIC_ROOT=f'{directory}/static', MEDIA_ROOT=f'{directory}/media',
        ), self.assertRaises(CommandError):
            call_command(
                'launch_readiness', allow_non_production=True,
                prepare_storage=True, stdout=StringIO(), stderr=StringIO(),
            )
