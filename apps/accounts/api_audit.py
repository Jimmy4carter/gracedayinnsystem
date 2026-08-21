import logging


logger = logging.getLogger(__name__)


class ApiAuditMixin:
    """Record successful API mutations without coupling domain apps to audit at import time."""

    def finalize_response(self, request, response, *args, **kwargs):
        response = super().finalize_response(request, response, *args, **kwargs)
        if request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and response.status_code < 400:
            self._record_api_audit(request, response)
        return response

    def _record_api_audit(self, request, response):
        if not request.user or not request.user.is_authenticated:
            return
        try:
            from apps.frontend.models import AuditLog

            response_data = getattr(response, 'data', None)
            response_id = response_data.get('id') if isinstance(response_data, dict) else None
            target_id = self.kwargs.get(getattr(self, 'lookup_url_kwarg', None) or 'pk') or response_id or ''
            model = getattr(getattr(self, 'queryset', None), 'model', None)
            AuditLog.objects.create(
                actor=request.user,
                event_type='security',
                action=f'api_{getattr(self, "action", request.method.lower())}',
                target_model=model.__name__ if model else self.__class__.__name__,
                target_id=str(target_id),
                details={
                    'method': request.method,
                    'path': request.path,
                    'status_code': response.status_code,
                },
                ip_address=request.META.get('REMOTE_ADDR'),
                user_agent=(request.META.get('HTTP_USER_AGENT') or '')[:255],
            )
        except Exception:
            logger.exception('Unable to record API audit event')
