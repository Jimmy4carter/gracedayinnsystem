from unittest.mock import patch

from django.test import TestCase

from .default_users import DEFAULT_USERS, ensure_default_users
from .models import GuestProfile, UserProfile


class DefaultDeploymentUserTests(TestCase):
    def password_environment(self):
        return {
            item['env']: f"GraceDay-{item['role']}-2026!{index}Xq"
            for index, item in enumerate(DEFAULT_USERS, start=1)
        }

    def test_default_accounts_are_created_and_idempotently_verified(self):
        with patch.dict('os.environ', self.password_environment(), clear=False):
            first = ensure_default_users()
            second = ensure_default_users()
        self.assertEqual(UserProfile.objects.count(), len(DEFAULT_USERS))
        self.assertTrue(all(item['status'] == 'created' for item in first))
        self.assertTrue(all(item['status'] == 'verified' for item in second))
        admin = UserProfile.objects.get(username='admin')
        self.assertTrue(admin.is_superuser)
        self.assertTrue(admin.is_staff)
        self.assertEqual(admin.email, 'admin@gracedayinn.com')
        self.assertTrue(UserProfile.objects.get(username='info').check_password('GraceDay-guest-2026!6Xq'))
        self.assertTrue(GuestProfile.objects.filter(user__username='info').exists())
        self.assertEqual(
            {item['role'] for item in DEFAULT_USERS},
            {value for value, _label in UserProfile.ROLE_CHOICES},
        )
