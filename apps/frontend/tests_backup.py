import json
import os
import tempfile
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase

from .backup import decrypt_file, encrypt_file


MYSQL_DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.mysql', 'NAME': 'gracedayinn',
        'USER': 'backup_user', 'PASSWORD': 'secret', 'HOST': 'localhost', 'PORT': 3306,
    }
}


class BackupControlTests(SimpleTestCase):
    def test_encryption_round_trip_and_wrong_key_rejection(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'source.dump'
            encrypted = Path(directory) / 'backup.gdi'
            restored = Path(directory) / 'restored.dump'
            source.write_bytes((b'mysql-logical-archive' * 1000))
            encrypt_file(source, encrypted, 'a-strong-backup-key-with-32-characters')
            self.assertNotIn(b'mysql-logical-archive', encrypted.read_bytes())
            decrypt_file(encrypted, restored, 'a-strong-backup-key-with-32-characters')
            self.assertEqual(restored.read_bytes(), source.read_bytes())
            with self.assertRaises(Exception):
                decrypt_file(encrypted, restored, 'a-different-strong-backup-key-1234')

    def test_backup_refuses_non_production_database(self):
        with tempfile.TemporaryDirectory() as directory, self.assertRaises(CommandError):
            call_command('create_encrypted_backup', output_dir=directory)

    @patch.dict(os.environ, {'BACKUP_ENCRYPTION_KEY': 'a-strong-backup-key-with-32-characters'})
    @patch('apps.frontend.management.commands.create_encrypted_backup.subprocess.run')
    def test_create_and_verify_mysql_commands_produce_authenticated_manifest(self, subprocess_run):
        def create_archive(command, **kwargs):
            if command[0] == 'mysqldump':
                Path(command[command.index('--result-file') + 1]).write_bytes(
                    b'-- MySQL dump 10.13\nCREATE TABLE `test` (`id` bigint);\n'
                )
        subprocess_run.side_effect = create_archive
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            settings.DATABASES, MYSQL_DATABASES, clear=True,
        ):
            output = StringIO()
            call_command('create_encrypted_backup', output_dir=directory, stdout=output)
            backup = next(Path(directory).glob('*.sql.gdi'))
            manifest = json.loads(Path(f'{backup}.json').read_text(encoding='utf-8'))
            self.assertEqual(manifest['format'], 'GDIBACKUP1')
            self.assertEqual(manifest['database'], 'gracedayinn')
            self.assertEqual(manifest['database_kind'], 'mysql')
            self.assertGreater(manifest['size_bytes'], 0)
            call_command('verify_encrypted_backup', backup_file=str(backup), stdout=StringIO())
            dump_call = subprocess_run.call_args
            self.assertEqual(dump_call.args[0][0], 'mysqldump')
            self.assertNotIn('secret', dump_call.args[0])
            self.assertEqual(dump_call.kwargs['env']['MYSQL_PWD'], 'secret')

            backup.write_bytes(backup.read_bytes() + b'tampered')
            with self.assertRaisesMessage(CommandError, 'checksum'):
                call_command('verify_encrypted_backup', backup_file=str(backup))
