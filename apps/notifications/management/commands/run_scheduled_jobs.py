from django.core.management.base import BaseCommand

from apps.notifications.jobs import run_due_jobs


class Command(BaseCommand):
    help = 'Claim and execute due database-backed jobs with retry/failure tracking.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=20)
        parser.add_argument('--job', dest='key')

    def handle(self, *args, **options):
        executions = run_due_jobs(limit=max(1, options['limit']), key=options.get('key'))
        failed = sum(item.status == 'failed' for item in executions)
        self.stdout.write(self.style.SUCCESS(
            f'Executed {len(executions)} scheduled job(s); {failed} failed.'
        ))
