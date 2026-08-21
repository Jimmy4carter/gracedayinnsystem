from types import SimpleNamespace

from django.test import SimpleTestCase
from rest_framework.routers import DefaultRouter

from apps.accounts.permissions import RoleActionPermission
from apps.accounts.urls import router as accounts_router
from apps.billing.urls import router as billing_router
from apps.housekeeping.urls import router as housekeeping_router
from apps.notifications.urls import router as notifications_router
from apps.payments.urls import router as payments_router
from apps.reservations.urls import router as reservations_router
from apps.rooms.urls import router as rooms_router
from apps.services.urls import router as services_router


class ApiPolicyCoverageTests(SimpleTestCase):
    routers = [
        accounts_router, billing_router, housekeeping_router, notifications_router,
        payments_router, reservations_router, rooms_router, services_router,
    ]
    valid_roles = {'admin', 'manager', 'receptionist', 'housekeeping', 'guest'}

    def test_every_routed_action_has_an_explicit_valid_role_policy(self):
        missing = []
        invalid = []
        for router in self.routers:
            self.assertIsInstance(router, DefaultRouter)
            for prefix, viewset, _basename in router.registry:
                routed_actions = {
                    action_name
                    for route in router.get_routes(viewset)
                    for action_name in route.mapping.values()
                    if hasattr(viewset, action_name)
                }
                policies = getattr(viewset, 'action_roles', {})
                for action_name in routed_actions:
                    if action_name not in policies:
                        missing.append(f'{prefix}:{action_name}')
                    elif not set(policies[action_name]).issubset(self.valid_roles):
                        invalid.append(f'{prefix}:{action_name}')
        self.assertEqual(missing, [], f'Routed API actions missing explicit policies: {missing}')
        self.assertEqual(invalid, [], f'Routed API actions contain unknown roles: {invalid}')

    def test_permission_matrix_default_denies_and_matches_every_declared_role(self):
        permission = RoleActionPermission()
        for router in self.routers:
            for prefix, viewset_class, _basename in router.registry:
                view = viewset_class()
                for action_name, allowed_roles in viewset_class.action_roles.items():
                    view.action = action_name
                    for role in self.valid_roles:
                        user = SimpleNamespace(is_authenticated=True, is_superuser=False, role=role)
                        request = SimpleNamespace(user=user)
                        with self.subTest(endpoint=prefix, action=action_name, role=role):
                            self.assertEqual(
                                permission.has_permission(request, view), role in allowed_roles,
                            )
                view.action = 'undeclared-action'
                guest = SimpleNamespace(is_authenticated=True, is_superuser=False, role='guest')
                self.assertFalse(permission.has_permission(SimpleNamespace(user=guest), view))
