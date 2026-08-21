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
    help = 'Create an encrypted MySQL or PostgreSQL logical backup and checksum manifest.'

    def add_arguments(self, parser):
        parser.add_argument('--output-dir', required=True)

    def handle(self, *args, **options):
        database = settings.DATABASES['default']
        engine = database['ENGINE']
        if engine not in {'django.db.backends.mysql', 'django.db.backends.postgresql'}:
            raise CommandError('Encrypted production backups require MySQL/MariaDB or PostgreSQL.')
        passphrase = os.environ.get('BACKUP_ENCRYPTION_KEY', '')
        if len(passphrase) < 24:
            raise CommandError('BACKUP_ENCRYPTION_KEY must contain at least 24 characters.')
        output_dir = Path(options['output_dir']).resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        database_kind = 'mysql' if engine == 'django.db.backends.mysql' else 'postgresql'
        plain_suffix = '.sql' if database_kind == 'mysql' else '.dump'
        destination = output_dir / f'gracedayinn-{stamp}{plain_suffix}.gdi'
        manifest_path = destination.with_suffix(destination.suffix + '.json')
        environment = os.environ.copy()
        if database_kind == 'mysql':
            environment['MYSQL_PWD'] = database.get('PASSWORD', '')
        else:
            environment['PGPASSWORD'] = database.get('PASSWORD', '')
        with tempfile.NamedTemporaryFile(suffix=plain_suffix, dir=output_dir, delete=False) as temporary:
            plain_path = Path(temporary.name)
        try:
            if database_kind == 'mysql':
                command = [
                    os.environ.get('MYSQL_DUMP_BINARY', 'mysqldump'),
                    '--single-transaction', '--quick', '--skip-lock-tables',
                    '--default-character-set=utf8mb4', '--host', database.get('HOST') or 'localhost',
                    '--port', str(database.get('PORT') or 3306), '--user', database.get('USER', ''),
                    '--result-file', str(plain_path), database['NAME'],
                ]
            else:
                command = [
                    'pg_dump', '--format=custom', '--no-owner', '--no-privileges',
                    '--file', str(plain_path), '--host', database.get('HOST') or 'localhost',
                    '--port', str(database.get('PORT') or 5432), '--username', database.get('USER', ''),
                    database['NAME'],
                ]
            subprocess.run(command, env=environment, check=True, capture_output=True, text=True)
            if not plain_path.exists() or plain_path.stat().st_size == 0:
                raise CommandError(f'{command[0]} produced an empty archive.')
            encrypt_file(plain_path, destination, passphrase)
        except (subprocess.CalledProcessError, OSError, ValueError) as exc:
            destination.unlink(missing_ok=True)
            detail = getattr(exc, 'stderr', '') or str(exc)
            raise CommandError(f'Backup failed: {detail[:500]}') from exc
        finally:
            plain_path.unlink(missing_ok=True)
        manifest = {
            'format': 'GDIBACKUP1', 'created_at': datetime.now(timezone.utc).isoformat(),
            'database': database['NAME'], 'database_kind': database_kind,
            'encrypted_file': destination.name,
            'sha256': sha256_file(destination), 'size_bytes': destination.stat().st_size,
        }
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
        self.stdout.write(self.style.SUCCESS(f'Encrypted backup created: {destination}'))
