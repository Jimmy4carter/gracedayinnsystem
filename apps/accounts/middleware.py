from django.contrib.auth import logout
from django.shortcuts import redirect

from .mfa import staff_mfa_required


class StaffMFASessionMiddleware:
    """Prevent an authenticated staff session from bypassing the MFA boundary."""

    EXEMPT_PREFIXES = (
        '/portal/sign-in/', '/portal/logout/', '/portal/mfa/',
        '/api/', '/health/', '/static/', '/media/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if (
            user.is_authenticated
            and staff_mfa_required(user)
            and not request.path.startswith(self.EXEMPT_PREFIXES)
            and request.session.get('staff_mfa_verified_user_id') != user.id
        ):
            logout(request)
            return redirect('frontend:portal-sign-in')
        return self.get_response(request)
