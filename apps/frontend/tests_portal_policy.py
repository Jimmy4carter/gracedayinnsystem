import re

from django.test import TestCase
from django.urls import URLPattern, URLResolver, reverse

from apps.accounts.models import UserProfile

from . import urls as frontend_urls


VALID_ROLES = {'admin', 'manager', 'receptionist', 'accountant', 'housekeeping', 'guest'}
PUBLIC_PORTAL_ROUTES = {
    'portal-sign-in', 'portal-sign-up', 'portal-verify-booking',
    'portal-mfa-challenge', 'portal-mfa-enroll', 'portal-set-password',
    'portal-password-reset',
}
DYNAMIC_NON_ACTION_ROUTES = {'portal-management-pack-download'}


def _portal_patterns(patterns, prefix=''):
    for entry in patterns:
        route = prefix + str(entry.pattern)
        if isinstance(entry, URLResolver):
            yield from _portal_patterns(entry.url_patterns, route)
        elif isinstance(entry, URLPattern) and route.startswith('portal/'):
            yield entry, route


def _callback_policy(callback, attribute):
    current = callback
    while current:
        value = getattr(current, attribute, None)
        if value is not None:
            return value
        current = getattr(current, '__wrapped__', None)
    return None


def _sample_path(route, action='policy-test'):
    values = {
        'int': '999999', 'uuid': '00000000-0000-0000-0000-000000000000',
        'str': action, 'slug': action,
    }

    def replace(match):
        converter = match.group(1) or 'str'
        return values[converter]

    return '/' + re.sub(r'<(?:(int|uuid|str|slug):)?[^>]+>', replace, route)


class PortalRoutePolicyContractTests(TestCase):
    def setUp(self):
        self.users = {
            role: UserProfile.objects.create_user(
                f'portal-policy-{role}', password='pass', role=role,
            ) for role in VALID_ROLES
        }

    def test_every_protected_portal_route_redirects_anonymous_users_to_sign_in(self):
        failures = []
        for pattern, route in _portal_patterns(frontend_urls.urlpatterns):
            if pattern.name in PUBLIC_PORTAL_ROUTES:
                continue
            response = self.client.get(_sample_path(route))
            if response.status_code != 302 or reverse('frontend:portal-sign-in') not in response.url:
                failures.append((pattern.name, route, response.status_code, getattr(response, 'url', '')))
        self.assertEqual(failures, [], f'Portal routes missing authentication boundary: {failures}')

    def test_every_dynamic_action_route_declares_complete_valid_role_policy(self):
        failures = []
        for pattern, route in _portal_patterns(frontend_urls.urlpatterns):
            if '<str:action>' not in route or pattern.name in DYNAMIC_NON_ACTION_ROUTES:
                continue
            policy = _callback_policy(pattern.callback, 'portal_action_roles')
            if not policy:
                failures.append((pattern.name, 'missing action policy'))
                continue
            for action, roles in policy.items():
                if not action or not roles or not set(roles).issubset(VALID_ROLES):
                    failures.append((pattern.name, action, sorted(roles)))
        self.assertEqual(failures, [], f'Invalid portal action policies: {failures}')

    def test_every_static_role_policy_uses_known_roles_and_denies_an_outside_role(self):
        failures = []
        for pattern, route in _portal_patterns(frontend_urls.urlpatterns):
            allowed = _callback_policy(pattern.callback, 'portal_allowed_roles')
            if allowed is None:
                continue
            if not allowed or not set(allowed).issubset(VALID_ROLES):
                failures.append((pattern.name, 'invalid roles', sorted(allowed)))
                continue
            denied_role = next((role for role in VALID_ROLES if role not in allowed), None)
            if denied_role is None:
                continue
            self.client.force_login(self.users[denied_role])
            response = self.client.get(_sample_path(route))
            if response.status_code != 302:
                failures.append((pattern.name, denied_role, response.status_code))
            self.client.logout()
        self.assertEqual(failures, [], f'Static portal role-policy failures: {failures}')

    def test_every_action_policy_denies_a_role_outside_its_allowlist_before_object_lookup(self):
        failures = []
        for pattern, route in _portal_patterns(frontend_urls.urlpatterns):
            policy = _callback_policy(pattern.callback, 'portal_action_roles')
            if not policy:
                continue
            for action, allowed in policy.items():
                denied_role = next((role for role in VALID_ROLES if role not in allowed), None)
                if denied_role is None:
                    continue
                self.client.force_login(self.users[denied_role])
                response = self.client.post(_sample_path(route, action=action))
                if response.status_code != 302:
                    failures.append((pattern.name, action, denied_role, response.status_code))
                self.client.logout()
        self.assertEqual(failures, [], f'Portal action denial failures: {failures}')

    def test_report_exports_enforce_roles_and_return_controlled_document_types(self):
        for role in ('guest', 'housekeeping'):
            self.client.force_login(self.users[role])
            self.assertEqual(self.client.get(reverse('frontend:portal-reports-export-csv')).status_code, 302)
            self.assertEqual(self.client.get(reverse('frontend:portal-reports-export-pdf')).status_code, 302)
        self.client.force_login(self.users['manager'])
        csv_response = self.client.get(reverse('frontend:portal-reports-export-csv'))
        pdf_response = self.client.get(reverse('frontend:portal-reports-export-pdf'))
        self.assertEqual(csv_response.status_code, 200)
        self.assertEqual(csv_response['Content-Type'], 'text/csv')
        self.assertIn('attachment;', csv_response['Content-Disposition'])
        self.client.force_login(self.users['accountant'])
        self.assertEqual(self.client.get(reverse('frontend:portal-reports-export-csv')).status_code, 200)
        self.assertEqual(pdf_response.status_code, 200)
        self.assertEqual(pdf_response['Content-Type'], 'application/pdf')
        self.assertIn('attachment;', pdf_response['Content-Disposition'])
