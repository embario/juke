#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-${REPO_ROOT}/backups}"
COMPOSE_FILE="${COMPOSE_FILE:-${REPO_ROOT}/docker-compose.prod.yml}"
ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.env}"

mkdir -p "${BACKUP_DIR}"

ts="$(date +%Y%m%d-%H%M%S)"
backup_path="${BACKUP_DIR}/postgres-${ts}.sql.gz"

echo "Saving backup to ${backup_path}..."
docker compose -f "${COMPOSE_FILE}" --env-file "${ENV_FILE}" exec -T db \
  pg_dump -U "${POSTGRES_USER:-postgres}" "${POSTGRES_NAME:-postgres}" | gzip > "${backup_path}"

echo "Backup complete."
