#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

LISTENBRAINZ_RUN_ID="${LISTENBRAINZ_RUN_ID:?LISTENBRAINZ_RUN_ID is required}"
LISTENBRAINZ_SOURCE_VERSION="${LISTENBRAINZ_SOURCE_VERSION:?LISTENBRAINZ_SOURCE_VERSION is required}"
MUSICBRAINZ_STAGE_RUN_ID="${MUSICBRAINZ_STAGE_RUN_ID:?MUSICBRAINZ_STAGE_RUN_ID is required}"
MUSICBRAINZ_SOURCE_VERSION="${MUSICBRAINZ_SOURCE_VERSION:?MUSICBRAINZ_SOURCE_VERSION is required}"
MUSICBRAINZ_MANIFEST="${MUSICBRAINZ_MANIFEST:?MUSICBRAINZ_MANIFEST is required}"

run_status() {
    local run_id="$1"
    docker compose exec -T db psql -U postgres -d postgres -Atc \
        "SELECT status FROM mlcore_source_ingestion_run WHERE id = '${run_id}'" 2>/dev/null || true
}

wait_for_run() {
    local label="$1"
    local run_id="$2"
    local status
    while true; do
        status="$(run_status "$run_id")"
        case "$status" in
            succeeded)
                echo "$(date --iso-8601=seconds) ${label} succeeded run_id=${run_id}"
                return 0
                ;;
            failed)
                echo "$(date --iso-8601=seconds) ${label} failed run_id=${run_id}" >&2
                return 1
                ;;
            *)
                echo "$(date --iso-8601=seconds) waiting for ${label} run_id=${run_id} status=${status:-unknown}"
                sleep 60
                ;;
        esac
    done
}

wait_for_run "ListenBrainz schema-v2 replay" "$LISTENBRAINZ_RUN_ID"
docker compose run --rm backend python manage.py materialize_listenbrainz_isrc_aliases \
    --source-version "$LISTENBRAINZ_SOURCE_VERSION" --json

wait_for_run "MusicBrainz stage" "$MUSICBRAINZ_STAGE_RUN_ID"
docker compose run --rm backend python manage.py import_musicbrainz_bridge \
    --manifest "$MUSICBRAINZ_MANIFEST" --json
docker compose run --rm backend python manage.py materialize_musicbrainz_isrc_aliases \
    --source-version "$MUSICBRAINZ_SOURCE_VERSION" --batch-size 100000 --json

docker compose run --rm backend python manage.py ingest_incremental_identity \
    --max-incrementals 14 --json

docker compose up -d worker beat
echo "$(date --iso-8601=seconds) ISRC coverage backfill and service recovery complete"
