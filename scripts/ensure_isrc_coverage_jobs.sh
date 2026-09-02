#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

if pgrep -f '/scripts/complete_isrc_coverage_backfill.sh' >/dev/null; then
    exit 0
fi

if docker ps --format '{{.Command}}' | grep -q 'ingest_incremental_identity'; then
    exit 0
fi

if docker compose ps --status running --services | grep -qx worker \
    && docker compose ps --status running --services | grep -qx beat; then
    exit 0
fi

systemctl --user --machine="${USER}@.host" start juke-isrc-incremental-catchup.service
