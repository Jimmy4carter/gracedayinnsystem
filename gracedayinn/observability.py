import contextvars
import json
import logging
import re
import time
import uuid
from datetime import datetime, timezone

from django.conf import settings
from opentelemetry import trace

request_id_context = contextvars.ContextVar('request_id', default='')
REQUEST_ID_PATTERN = re.compile(r'^[A-Za-z0-9._-]{8,80}$')


class JsonLogFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            'timestamp': datetime.now(timezone.utc).isoformat(),
            'level': record.levelname, 'logger': record.name,
            'message': record.getMessage(),
            'request_id': getattr(record, 'request_id', '') or request_id_context.get(),
            'release': getattr(settings, 'RELEASE_VERSION', 'development'),
        }
        span_context = trace.get_current_span().get_span_context()
        if span_context.is_valid:
            payload['trace_id'] = format(span_context.trace_id, '032x')
            payload['span_id'] = format(span_context.span_id, '016x')
        for field in ('method', 'path', 'status_code', 'duration_ms', 'actor_id', 'event'):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload['exception'] = record.exc_info[0].__name__
        return json.dumps(payload, default=str, separators=(',', ':'))


class RequestObservabilityMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.logger = logging.getLogger('gracedayinn.request')

    def __call__(self, request):
        supplied = request.headers.get('X-Request-ID', '')
        request_id = supplied if REQUEST_ID_PATTERN.fullmatch(supplied) else str(uuid.uuid4())
        request.request_id = request_id
        token = request_id_context.set(request_id)
        started = time.perf_counter()
        try:
            response = self.get_response(request)
        except Exception:
            self.logger.exception('request_failed', extra=self._extra(request, 500, started, 'request_failed'))
            raise
        else:
            response['X-Request-ID'] = request_id
            level = logging.WARNING if response.status_code >= 400 else logging.INFO
            self.logger.log(level, 'request_completed', extra=self._extra(
                request, response.status_code, started, 'request_completed'
            ))
            return response
        finally:
            request_id_context.reset(token)

    @staticmethod
    def _extra(request, status_code, started, event):
        user = getattr(request, 'user', None)
        return {
            'request_id': getattr(request, 'request_id', ''), 'method': request.method,
            'path': request.path, 'status_code': status_code,
            'duration_ms': round((time.perf_counter() - started) * 1000, 2),
            'actor_id': user.pk if user and user.is_authenticated else None, 'event': event,
        }
