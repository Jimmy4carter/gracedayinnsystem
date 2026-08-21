from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError

from apps.accounts.default_users import ensure_default_users


class Command(BaseCommand):
    help = 'Idempotently create and verify the required GraceDay deployment accounts.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--generate-missing', action='store_true',
            help='Generate strong one-time passwords for missing environment variables.',
        )

    def handle(self, *args, **options):
        try:
            results = ensure_default_users(generate_missing=options['generate_missing'])
        except ValidationError as exc:
            raise CommandError('; '.join(exc.messages)) from exc
        skipped = [item['env'] for item in results if item['status'] == 'skipped']
        if skipped:
            raise CommandError(f"Missing password environment variables: {', '.join(skipped)}")
        for item in results:
            line = f"{item['status'].upper()}: {item['username']} <{item['email']}> ({item['role']})"
            if item['password']:
                line += f" | one-time password: {item['password']}"
            self.stdout.write(self.style.SUCCESS(line))
        self.stdout.write(self.style.WARNING('Store generated credentials securely and change them after first sign-in.'))
