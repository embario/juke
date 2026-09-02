#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

docker compose run --rm backend python manage.py ingest_incremental_identity \
    --max-incrementals 14 --json
docker compose up -d worker beat
