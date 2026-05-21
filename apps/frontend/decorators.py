from functools import wraps

from django.contrib import messages
from django.shortcuts import redirect


def role_required(roles, redirect_route='frontend:portal-dashboard'):
    role_set = set(roles)

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            if request.user.role not in role_set:
                messages.error(request, 'You do not have permission to perform this action.')
                return redirect(redirect_route)
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator


def action_role_required(action_roles, action_kwarg='action', redirect_route='frontend:portal-dashboard'):
    normalized = {key: set(value) for key, value in action_roles.items()}

    def decorator(view_func):
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            action = kwargs.get(action_kwarg)
            allowed_roles = normalized.get(action)
            if allowed_roles is None:
                messages.error(request, 'Unknown action.')
                return redirect(redirect_route)
            if request.user.role not in allowed_roles:
                messages.error(request, 'You do not have permission to perform this action.')
                return redirect(redirect_route)
            return view_func(request, *args, **kwargs)

        return _wrapped

    return decorator
