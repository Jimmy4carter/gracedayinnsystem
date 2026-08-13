from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.frontend.reporting import generate_management_pack


class Command(BaseCommand):
    help = 'Generate an immutable PDF/CSV manager pack for a completed business date.'

    def add_arguments(self, parser):
        parser.add_argument('--date', dest='business_date')
        parser.add_argument('--retention-days', type=int, default=30)

    def handle(self, *args, **options):
        business_date = parse_date(options.get('business_date') or '') or (timezone.localdate() - timedelta(days=1))
        if business_date >= timezone.localdate():
            raise CommandError('Manager packs can only cover completed business dates.')
        pack, created = generate_management_pack(
            business_date=business_date, retention_days=max(1, options['retention_days'])
        )
        state = 'generated' if created else 'already exists'
        self.stdout.write(self.style.SUCCESS(f'Manager pack {pack.business_date} {state}.'))
