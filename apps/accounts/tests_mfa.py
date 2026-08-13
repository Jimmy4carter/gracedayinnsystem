import time

from django.contrib.auth.hashers import check_password
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken

from apps.frontend.models import AuditLog

from .mfa import (
    begin_mfa_enrollment, confirm_mfa_enrollment, current_totp,
    reset_mfa, verify_mfa_code,
)
from .models import StaffMFADevice, UserProfile


MFA_SETTINGS = override_settings(
    MFA_ENCRYPTION_KEY='test-mfa-encryption-key-that-is-long-enough',
    MFA_MAX_ATTEMPTS=2,
    MFA_LOCK_MINUTES=10,
)


@MFA_SETTINGS
class MFAServiceTests(TestCase):
    def setUp(self):
        self.staff = UserProfile.objects.create_user(
            'mfa-staff', password='strong-pass-123', role='manager',
            email='manager@example.com',
        )
        self.admin = UserProfile.objects.create_user(
            'mfa-admin', password='strong-pass-123', role='admin', is_superuser=True,
        )

    def enroll(self):
        _device, secret, _uri = begin_mfa_enrollment(user=self.staff)
        return secret, confirm_mfa_enrollment(
            user=self.staff, code=current_totp(secret), actor=self.staff,
        )[1]

    def test_secret_is_encrypted_and_recovery_codes_are_hashed_and_single_use(self):
        secret, recovery_codes = self.enroll()
        device = StaffMFADevice.objects.get(user=self.staff)
        self.assertNotIn(secret.encode(), bytes(device.encrypted_secret))
        self.assertNotIn(recovery_codes[0], device.recovery_code_hashes)
        self.assertTrue(check_password(recovery_codes[0], device.recovery_code_hashes[0]))
        self.assertTrue(verify_mfa_code(user=self.staff, code=recovery_codes[0]))
        with self.assertRaises(ValidationError):
            verify_mfa_code(user=self.staff, code=recovery_codes[0])

    def test_totp_replay_is_rejected_and_next_window_is_accepted(self):
        secret, _codes = self.enroll()
        future = time.time() + 30
        code = current_totp(secret, at=future)
        self.assertTrue(verify_mfa_code(user=self.staff, code=code, now=future))
        with self.assertRaises(ValidationError):
            verify_mfa_code(user=self.staff, code=code, now=future)

    def test_repeated_failures_temporarily_lock_device(self):
        _secret, _codes = self.enroll()
        for _ in range(2):
            with self.assertRaises(ValidationError):
                verify_mfa_code(user=self.staff, code='000000')
        device = StaffMFADevice.objects.get(user=self.staff)
        self.assertIsNotNone(device.locked_until)
        with self.assertRaisesMessage(ValidationError, 'temporarily locked'):
            verify_mfa_code(user=self.staff, code='000000')

    def test_only_admin_can_reset_and_reset_is_audited(self):
        self.enroll()
        with self.assertRaises(ValidationError):
            reset_mfa(user=self.staff, actor=self.staff, reason='Lost phone')
        reset_mfa(user=self.staff, actor=self.admin, reason='Identity verified at front desk')
        self.assertFalse(StaffMFADevice.objects.filter(user=self.staff).exists())
        self.assertTrue(AuditLog.objects.filter(action='mfa_reset', actor=self.admin).exists())


@MFA_SETTINGS
@override_settings(STAFF_MFA_REQUIRED=True)
class MFAPortalTests(TestCase):
    def setUp(self):
        self.staff = UserProfile.objects.create_user(
            'portal-mfa', password='strong-pass-123', role='receptionist',
        )

    def test_required_staff_login_enrolls_before_session_authentication(self):
        response = self.client.post(reverse('frontend:portal-sign-in'), {
            'username': self.staff.username, 'password': 'strong-pass-123',
        })
        self.assertRedirects(response, reverse('frontend:portal-mfa-enroll'), fetch_redirect_response=False)
        self.assertNotIn('_auth_user_id', self.client.session)

        enrollment = self.client.get(reverse('frontend:portal-mfa-enroll'))
        secret = enrollment.context['mfa_secret']
        response = self.client.post(reverse('frontend:portal-mfa-enroll'), {
            'code': current_totp(secret),
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['mode'], 'recovery')
        self.assertEqual(int(self.client.session['_auth_user_id']), self.staff.id)
        self.assertEqual(self.client.session['staff_mfa_verified_user_id'], self.staff.id)
        self.assertContains(response, 'Store these one-time recovery codes')

    def test_existing_staff_session_cannot_bypass_required_mfa(self):
        self.client.force_login(self.staff)
        response = self.client.get(reverse('frontend:portal-dashboard'))
        self.assertRedirects(response, reverse('frontend:portal-sign-in'), fetch_redirect_response=False)
        self.assertNotIn('_auth_user_id', self.client.session)


@MFA_SETTINGS
@override_settings(STAFF_MFA_REQUIRED=True)
class MFAApiTests(APITestCase):
    def setUp(self):
        self.staff = UserProfile.objects.create_user(
            'api-mfa', password='strong-pass-123', role='manager',
        )
        self.guest = UserProfile.objects.create_user(
            'api-guest-mfa', password='strong-pass-123', role='guest',
        )

    def test_staff_api_requires_enrollment_and_code_while_guest_does_not(self):
        response = self.client.post(reverse('api-login'), {
            'username': self.staff.username, 'password': 'strong-pass-123',
        })
        self.assertEqual(response.status_code, 400)
        self.assertIn('enrollment', str(response.data).lower())

        _device, secret, _uri = begin_mfa_enrollment(user=self.staff)
        recovery = confirm_mfa_enrollment(
            user=self.staff, code=current_totp(secret), actor=self.staff,
        )[1][0]
        self.assertEqual(self.client.post(reverse('api-login'), {
            'username': self.staff.username, 'password': 'strong-pass-123',
        }).status_code, 400)
        response = self.client.post(reverse('api-login'), {
            'username': self.staff.username, 'password': 'strong-pass-123',
            'mfa_code': recovery,
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('access', response.data)

        guest_response = self.client.post(reverse('api-login'), {
            'username': self.guest.username, 'password': 'strong-pass-123',
        })
        self.assertEqual(guest_response.status_code, 200)

    def test_logout_blacklists_refresh_token_and_rejects_reuse(self):
        login_response = self.client.post(reverse('api-login'), {
            'username': self.guest.username, 'password': 'strong-pass-123',
        })
        refresh = login_response.data['refresh']
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_response.data['access']}")
        response = self.client.post(reverse('api-logout'), {'refresh': refresh})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(BlacklistedToken.objects.count(), 1)
        self.client.credentials()
        self.assertEqual(self.client.post(reverse('token_refresh'), {'refresh': refresh}).status_code, 401)

    def test_logout_rejects_missing_or_invalid_refresh_token(self):
        login_response = self.client.post(reverse('api-login'), {
            'username': self.guest.username, 'password': 'strong-pass-123',
        })
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_response.data['access']}")
        self.assertEqual(self.client.post(reverse('api-logout'), {}).status_code, 400)
        self.assertEqual(self.client.post(reverse('api-logout'), {'refresh': 'invalid'}).status_code, 400)
