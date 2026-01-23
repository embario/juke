#!/bin/bash
set -euo pipefail

# Always operate from the backend directory
cd "$(dirname "$0")"

until python manage.py migrate --noinput; do
    echo "Waiting to connect to DB..."
    sleep 1
done

python manage.py collectstatic --noinput

GUNICORN_WORKERS="${GUNICORN_WORKERS:-3}"
GUNICORN_TIMEOUT="${GUNICORN_TIMEOUT:-60}"

exec gunicorn settings.wsgi:application \
    --bind 0.0.0.0:${BACKEND_PORT:?Set BACKEND_PORT} \
    --workers "${GUNICORN_WORKERS}" \
    --timeout "${GUNICORN_TIMEOUT}"
