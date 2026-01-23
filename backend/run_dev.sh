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

python manage.py runserver 0.0.0.0:${BACKEND_PORT:?Set BACKEND_PORT}
