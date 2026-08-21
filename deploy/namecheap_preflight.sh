#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${GRACEDAY_PYTHON:-python3}"
export DJANGO_SETTINGS_MODULE="gracedayinn.settings.prod"

"${PYTHON_BIN}" manage.py check --deploy --settings=gracedayinn.settings.prod
"${PYTHON_BIN}" manage.py makemigrations --check --dry-run
"${PYTHON_BIN}" manage.py migrate --plan

echo "Production preflight passed."
