from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.frontend.audit import verify_audit_chain


class Command(BaseCommand):
    help = 'Verify the append-only audit sequence, hash links, event payload hashes, and chain head.'

    def handle(self, *args, **options):
        try:
            result = verify_audit_chain()
        except ValidationError as exc:
            raise CommandError('; '.join(exc.messages)) from exc
        self.stdout.write(self.style.SUCCESS(
            f"Audit chain verified: {result['events_checked']} event(s), "
            f"head {result['last_hash']}."
        ))
