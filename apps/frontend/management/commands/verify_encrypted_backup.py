import json
import os
import subprocess
import tempfile
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.frontend.backup import decrypt_file, sha256_file


class Command(BaseCommand):
    help = 'Verify an encrypted backup checksum, authentication tag and pg_restore catalog.'

    def add_arguments(self, parser):
        parser.add_argument('--backup-file', required=True)

    def handle(self, *args, **options):
        backup = Path(options['backup_file']).resolve()
        manifest_path = backup.with_suffix(backup.suffix + '.json')
        if not backup.is_file() or not manifest_path.is_file():
            raise CommandError('Backup file and adjacent .json manifest are required.')
        passphrase = os.environ.get('BACKUP_ENCRYPTION_KEY', '')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
        if sha256_file(backup) != manifest.get('sha256'):
            raise CommandError('Backup checksum does not match its manifest.')
        with tempfile.NamedTemporaryFile(suffix='.dump', delete=False) as temporary:
            plain_path = Path(temporary.name)
        try:
            decrypt_file(backup, plain_path, passphrase)
            subprocess.run(
                ['pg_restore', '--list', str(plain_path)], check=True,
                capture_output=True, text=True,
            )
        except Exception as exc:
            detail = getattr(exc, 'stderr', '') or str(exc)
            raise CommandError(f'Backup verification failed: {detail[:500]}') from exc
        finally:
            plain_path.unlink(missing_ok=True)
        self.stdout.write(self.style.SUCCESS(f'Backup verified: {backup}'))
