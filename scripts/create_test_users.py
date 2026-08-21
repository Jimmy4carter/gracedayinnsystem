"""Compatibility wrapper for creating the six canonical local test accounts.

Passwords are generated at runtime and printed once. No reusable password is kept in source.
Production deployment should use per-role DEFAULT_*_PASSWORD environment variables instead.
"""

import os
import sys
from pathlib import Path

import django
from django.core.management import call_command


PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gracedayinn.settings.base')
django.setup()

call_command('ensure_default_users', '--generate-missing')
