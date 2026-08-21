class HotelAdminPermissionMixin:
    """Keep Django admin read-only for managers and mutable only for administrators."""

    def _is_admin(self, request):
        return request.user.is_superuser or getattr(request.user, 'role', None) == 'admin'

    def _can_view(self, request):
        return self._is_admin(request) or getattr(request.user, 'role', None) == 'manager'

    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_staff and self._can_view(request)

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff and self._can_view(request)

    def has_add_permission(self, request):
        return request.user.is_active and request.user.is_staff and self._is_admin(request)

    def has_change_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff and self._is_admin(request)

    def has_delete_permission(self, request, obj=None):
        return request.user.is_active and request.user.is_staff and self._is_admin(request)
