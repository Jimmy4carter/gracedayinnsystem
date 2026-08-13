import json
import os
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.frontend.backup import encrypt_file, sha256_file


class Command(BaseCommand):
    help = 'Create an encrypted PostgreSQL custom-format backup and checksum manifest.'

    def add_arguments(self, parser):
        parser.add_argument('--output-dir', required=True)

    def handle(self, *args, **options):
        database = settings.DATABASES['default']
        if database['ENGINE'] != 'django.db.backends.postgresql':
            raise CommandError('Encrypted production backups require a PostgreSQL database.')
        passphrase = os.environ.get('BACKUP_ENCRYPTION_KEY', '')
        if len(passphrase) < 24:
            raise CommandError('BACKUP_ENCRYPTION_KEY must contain at least 24 characters.')
        output_dir = Path(options['output_dir']).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        destination = output_dir / f'gracedayinn-{stamp}.dump.gdi'
        manifest_path = destination.with_suffix(destination.suffix + '.json')
        environment = os.environ.copy()
        environment['PGPASSWORD'] = database.get('PASSWORD', '')
        with tempfile.NamedTemporaryFile(suffix='.dump', dir=output_dir, delete=False) as temporary:
            plain_path = Path(temporary.name)
        try:
            command = [
                'pg_dump', '--format=custom', '--no-owner', '--no-privileges',
                '--file', str(plain_path), '--host', database.get('HOST') or 'localhost',
                '--port', str(database.get('PORT') or 5432), '--username', database.get('USER', ''),
                database['NAME'],
            ]
            subprocess.run(command, env=environment, check=True, capture_output=True, text=True)
            if not plain_path.exists() or plain_path.stat().st_size == 0:
                raise CommandError('pg_dump produced an empty archive.')
            encrypt_file(plain_path, destination, passphrase)
        except (subprocess.CalledProcessError, OSError, ValueError) as exc:
            destination.unlink(missing_ok=True)
            detail = getattr(exc, 'stderr', '') or str(exc)
            raise CommandError(f'Backup failed: {detail[:500]}') from exc
        finally:
            plain_path.unlink(missing_ok=True)
        manifest = {
            'format': 'GDIBACKUP1', 'created_at': datetime.now(timezone.utc).isoformat(),
            'database': database['NAME'], 'encrypted_file': destination.name,
            'sha256': sha256_file(destination), 'size_bytes': destination.stat().st_size,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'Encrypted backup created: {destination}'))
