from datetime import timedelta

from django.core.cache import cache
from django.db import connection
from django.http import JsonResponse
from django.utils import timezone


def liveness(request):
    return JsonResponse({'status': 'alive'})


def readiness(request):
    checks = {}
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
            cursor.fetchone()
        checks['database'] = 'ok'
    except Exception:
        checks['database'] = 'failed'
    try:
        key = 'health:readiness'
        value = str(timezone.now().timestamp())
        cache.set(key, value, 10)
        checks['cache'] = 'ok' if cache.get(key) == value else 'failed'
        cache.delete(key)
    except Exception:
        checks['cache'] = 'failed'
    try:
        from apps.notifications.models import ScheduledJob
        stale = []
        now = timezone.now()
        for job in ScheduledJob.objects.filter(is_enabled=True):
            grace = timedelta(minutes=max(30, job.interval_minutes * 2))
            if job.next_run_at < now - grace:
                stale.append(job.key)
        checks['scheduler'] = 'ok' if not stale else 'stale'
        if stale:
            checks['stale_jobs'] = stale
    except Exception:
        checks['scheduler'] = 'failed'
    ready = all(checks.get(name) == 'ok' for name in ('database', 'cache', 'scheduler'))
    return JsonResponse({'status': 'ready' if ready else 'not_ready', 'checks': checks}, status=200 if ready else 503)
