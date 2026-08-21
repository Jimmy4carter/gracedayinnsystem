#!/usr/bin/env bash
set -Eeuo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
APP_NAME="$(basename "${PROJECT_ROOT}")"
ACCOUNT_ROOT="$(dirname "${PROJECT_ROOT}")"

cd "${PROJECT_ROOT}"

find_python() {
    if [[ -n "${GRACEDAY_PYTHON:-}" ]]; then
        if [[ ! -x "${GRACEDAY_PYTHON}" ]]; then
            echo "GRACEDAY_PYTHON is not executable: ${GRACEDAY_PYTHON}" >&2
            return 1
        fi
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
    echo "Set GRACEDAY_PYTHON to its absolute python path in the deployment environment." >&2
    return 1
}

PYTHON_BIN="$(find_python)"
export DJANGO_SETTINGS_MODULE="gracedayinn.settings.prod"

echo "Deploying GraceDay Inn from ${PROJECT_ROOT}"
echo "Using Python: ${PYTHON_BIN}"

if [[ "${GRACEDAY_SKIP_PIP:-0}" != "1" ]]; then
    "${PYTHON_BIN}" -m pip install --disable-pip-version-check -r requirements.txt
fi

"${PYTHON_BIN}" manage.py check --deploy --settings=gracedayinn.settings.prod
"${PYTHON_BIN}" manage.py migrate --noinput
"${PYTHON_BIN}" manage.py createcachetable
"${PYTHON_BIN}" manage.py reconcile_system
"${PYTHON_BIN}" manage.py ensure_default_users
"${PYTHON_BIN}" manage.py collectstatic --noinput

mkdir -p tmp
touch tmp/restart.txt

echo "Deployment completed. Passenger restart requested."
