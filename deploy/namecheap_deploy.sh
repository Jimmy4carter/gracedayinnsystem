#!/usr/bin/env bash
set -Eeuo pipefail
umask 027

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
APP_NAME="$(basename "${PROJECT_ROOT}")"
ACCOUNT_ROOT="$(dirname "${PROJECT_ROOT}")"

cd "${PROJECT_ROOT}"

CURRENT_BRANCH="$(git branch --show-current)"
if [[ "${CURRENT_BRANCH}" != "production" ]]; then
    echo "Refusing to deploy branch '${CURRENT_BRANCH}'. Namecheap deploys production only." >&2
    exit 1
fi

mkdir -p tmp
LOCK_DIR="tmp/deployment.lock"
if ! mkdir "${LOCK_DIR}" 2>/dev/null; then
    echo "Another deployment appears to be running (${LOCK_DIR} exists)." >&2
    exit 1
fi
trap 'rmdir "${LOCK_DIR}" 2>/dev/null || true' EXIT

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
export RELEASE_VERSION="${RELEASE_VERSION:-$(git rev-parse --short=12 HEAD)}"

echo "Deploying GraceDay Inn from ${PROJECT_ROOT}"
echo "Using Python: ${PYTHON_BIN}"
echo "Release: ${RELEASE_VERSION}"

if [[ "${GRACEDAY_SKIP_PIP:-0}" != "1" ]]; then
    "${PYTHON_BIN}" -m pip install --disable-pip-version-check -r requirements.txt
fi

"${PYTHON_BIN}" manage.py check --deploy --settings=gracedayinn.settings.prod
"${PYTHON_BIN}" -c "from app import application; assert callable(application)"
"${PYTHON_BIN}" manage.py makemigrations --check --dry-run
"${PYTHON_BIN}" manage.py collectstatic --noinput
"${PYTHON_BIN}" manage.py migrate --plan
"${PYTHON_BIN}" manage.py migrate --noinput
"${PYTHON_BIN}" manage.py createcachetable
"${PYTHON_BIN}" manage.py ensure_default_users
"${PYTHON_BIN}" manage.py launch_readiness --prepare-storage

touch tmp/restart.txt

echo "Deployment completed. Passenger restart requested."
