from django.core.management.base import BaseCommand

from apps.notifications.services import process_due_outbox


class Command(BaseCommand):
    help = 'Process queued and retryable outbound email messages.'

    def add_arguments(self, parser):
        parser.add_argument('--limit', type=int, default=100)

    def handle(self, *args, **options):
        messages = process_due_outbox(limit=max(1, options['limit']))
        self.stdout.write(self.style.SUCCESS(f'Processed {len(messages)} outbound message(s).'))
