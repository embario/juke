#!/bin/bash
set -euo pipefail

# Always operate from the backend directory
cd "$(dirname "$0")"

# wait for the database

until python manage.py migrate
do
	echo "Waiting to connect to DB..."
	sleep 1
done

python manage.py loaddata dev.json

if [[ "${JUKE_WORLD_SEED_COUNT:-}" =~ ^[0-9]+$ ]] && [[ "${JUKE_WORLD_SEED_COUNT}" -gt 0 ]]; then
	echo "Seeding ${JUKE_WORLD_SEED_COUNT} Juke World users..."
	python manage.py seed_world_data --count "${JUKE_WORLD_SEED_COUNT}" --clear
fi

python manage.py runserver 0.0.0.0:${BACKEND_PORT:?Set BACKEND_PORT}
