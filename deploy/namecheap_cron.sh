#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
APP_NAME="$(basename "${PROJECT_ROOT}")"
ACCOUNT_ROOT="$(dirname "${PROJECT_ROOT}")"

find_python() {
    if [[ -n "${GRACEDAY_PYTHON:-}" && -x "${GRACEDAY_PYTHON}" ]]; then
        printf '%s\n' "${GRACEDAY_PYTHON}"
        return
    fi

    local candidates=()
    shopt -s nullglob
    candidates=("${ACCOUNT_ROOT}/virtualenv/${APP_NAME}"/*/bin/python)
    shopt -u nullglob
    if (( ${#candidates[@]} > 0 )); then
        printf '%s\n' "${candidates[${#candidates[@]} - 1]}"
        return
    fi

    echo "Unable to locate the cPanel Python virtual environment." >&2
    return 1
}

cd "${PROJECT_ROOT}"
export DJANGO_SETTINGS_MODULE="gracedayinn.settings.prod"
PYTHON_BIN="$(find_python)"
"${PYTHON_BIN}" manage.py run_scheduled_jobs --limit "${GRACEDAY_JOB_LIMIT:-20}"
