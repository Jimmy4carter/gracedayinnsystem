"""CloudLinux/cPanel startup module for the GraceDay Inn WSGI application."""

import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'gracedayinn.settings.prod')

from gracedayinn.wsgi import application  # noqa: E402,F401
