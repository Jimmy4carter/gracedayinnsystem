import json

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.frontend.reconciliation import reconcile_system


class Command(BaseCommand):
    help = 'Reconcile migration, inventory, financial, stock, and audit invariants.'

    def add_arguments(self, parser):
        parser.add_argument('--json', action='store_true', dest='as_json')

    def handle(self, *args, **options):
        try:
            result = reconcile_system()
        except ValidationError as exc:
            raise CommandError('; '.join(exc.messages)) from exc

        if options['as_json']:
            self.stdout.write(json.dumps(result, sort_keys=True, default=str))
        else:
            self.stdout.write(
                f"Database: {result['database_vendor']}; "
                f"models: {len(result['counts'])}; "
                f"audit events: {result['audit']['events_checked']}."
            )
        if not result['ok']:
            populated = {key: value for key, value in result['issues'].items() if value}
            raise CommandError(f'Reconciliation failed: {json.dumps(populated, default=str)}')
        self.stdout.write(self.style.SUCCESS('System reconciliation passed.'))
