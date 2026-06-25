#!/usr/bin/env bash
set -euo pipefail
umask 022

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-${REPO_ROOT}/docker-compose.yml}"
ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.env}"
METRICS_PATH="${1:-${JUKE_HOST_NODE_EXPORTER_TEXTFILE_PATH:-/srv/monitoring/node-exporter/textfile}/mlcore_identity.prom}"

compose_cmd=(docker compose -f "${COMPOSE_FILE}")
if [[ -f "${ENV_FILE}" ]]; then
    compose_cmd+=(--env-file "${ENV_FILE}")
fi

mkdir -p "$(dirname "${METRICS_PATH}")"
tmp_path="${METRICS_PATH}.tmp"

"${compose_cmd[@]}" exec -T db bash <<'SCRIPT' >"${tmp_path}"
set -euo pipefail

DB_NAME="${POSTGRES_NAME:-postgres}"
DB_USER="${POSTGRES_USER:-postgres}"

psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" -At <<'SQL'
with metric_lines(ord, line) as (
  values
    (100, '# HELP mlcore_canonical_items Canonical item count by item type.'),
    (101, '# TYPE mlcore_canonical_items gauge')
  union all
  select
    110,
    format('mlcore_canonical_items{item_type="%s"} %s', item_type, count(*))
  from mlcore_canonical_item
  group by item_type
  union all
  values
    (200, '# HELP mlcore_canonical_aliases Canonical alias count by source and resource type.'),
    (201, '# TYPE mlcore_canonical_aliases gauge')
  union all
  select
    210,
    format(
      'mlcore_canonical_aliases{source="%s",resource_type="%s",status="%s"} %s',
      source,
      resource_type,
      status,
      count(*)
    )
  from mlcore_canonical_item_alias
  group by source, resource_type, status
  union all
  values
    (300, '# HELP mlcore_musicbrainz_isrc_rows MusicBrainz recording to ISRC evidence rows.'),
    (301, '# TYPE mlcore_musicbrainz_isrc_rows gauge')
  union all
  select 310, format('mlcore_musicbrainz_isrc_rows %s', count(*))
  from mlcore_musicbrainz_recording_isrc
  union all
  values
    (400, '# HELP mlcore_musicbrainz_unique_isrcs Distinct ISRC values in MusicBrainz evidence.'),
    (401, '# TYPE mlcore_musicbrainz_unique_isrcs gauge')
  union all
  select 410, format('mlcore_musicbrainz_unique_isrcs %s', count(distinct isrc))
  from mlcore_musicbrainz_recording_isrc
  union all
  values
    (500, '# HELP mlcore_identity_redirects Canonical redirect count by source and status.'),
    (501, '# TYPE mlcore_identity_redirects gauge')
  union all
  select
    510,
    format('mlcore_identity_redirects{source="%s",status="%s"} %s', source, status, count(*))
  from mlcore_canonical_item_redirect
  group by source, status
  union all
  values
    (600, '# HELP mlcore_listenbrainz_msid_mbid_mappings ListenBrainz MSID to MBID mapping rows by source version and status.'),
    (601, '# TYPE mlcore_listenbrainz_msid_mbid_mappings gauge')
  union all
  select
    610,
    format(
      'mlcore_listenbrainz_msid_mbid_mappings{source_version="%s",status="%s"} %s',
      source_version,
      status,
      count(*)
    )
  from mlcore_listenbrainz_msid_mbid_mapping
  group by source_version, status
  union all
  values
    (700, '# HELP mlcore_listenbrainz_conflict_resolutions ListenBrainz conflict resolution rows by policy and status.'),
    (701, '# TYPE mlcore_listenbrainz_conflict_resolutions gauge')
  union all
  select
    710,
    format(
      'mlcore_listenbrainz_conflict_resolutions{policy_version="%s",status="%s"} %s',
      policy_version,
      status,
      count(*)
    )
  from mlcore_listenbrainz_msid_mbid_conflict_resolution
  group by policy_version, status
)
select line from metric_lines order by ord, line;
SQL
SCRIPT

mv "${tmp_path}" "${METRICS_PATH}"
echo "wrote ${METRICS_PATH}"
