from rest_framework.permissions import BasePermission


def has_role(user, roles):
    """Return whether an authenticated user belongs to one of the allowed hotel roles."""
    return bool(
        user
        and user.is_authenticated
        and (user.is_superuser or getattr(user, 'role', None) in set(roles))
    )


class RoleActionPermission(BasePermission):
    """Default-deny DRF permission driven by a viewset's ``action_roles`` map."""

    message = 'You do not have permission to perform this action.'

    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        if request.user.is_superuser:
            return True

        action = getattr(view, 'action', None)
        allowed_roles = getattr(view, 'action_roles', {}).get(action)
        if allowed_roles is None:
            return False
        return getattr(request.user, 'role', None) in allowed_roles
