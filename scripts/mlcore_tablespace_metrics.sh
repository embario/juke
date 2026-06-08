#!/usr/bin/env bash
set -euo pipefail
umask 022

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-${REPO_ROOT}/docker-compose.yml}"
ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.env}"
METRICS_PATH="${1:-${JUKE_HOST_NODE_EXPORTER_TEXTFILE_PATH:-/srv/monitoring/node-exporter/textfile}/mlcore_tablespace.prom}"

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
with table_stats as (
  select
    c.relname as table_name,
    coalesce(ts.spcname, 'pg_default') as tablespace,
    pg_relation_size(c.oid) as table_bytes,
    pg_indexes_size(c.oid) as index_bytes,
    pg_total_relation_size(c.oid) as total_bytes,
    greatest(c.reltuples, 0)::bigint as estimated_rows
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  left join pg_tablespace ts on ts.oid = c.reltablespace
  where n.nspname = 'public'
    and c.relkind = 'r'
    and c.relname like 'mlcore_%'
),
tablespace_totals as (
  select
    tablespace,
    sum(table_bytes) as table_bytes,
    sum(index_bytes) as index_bytes,
    sum(total_bytes) as total_bytes,
    sum(estimated_rows) as estimated_rows
  from table_stats
  group by tablespace
)
select '# HELP mlcore_table_bytes PostgreSQL heap bytes for MLCore tables.'
union all select '# TYPE mlcore_table_bytes gauge'
union all
select format(
  'mlcore_table_bytes{tablespace="%s",table="%s"} %s',
  tablespace,
  table_name,
  table_bytes
)
from table_stats
union all select '# HELP mlcore_table_index_bytes PostgreSQL index bytes for MLCore tables.'
union all select '# TYPE mlcore_table_index_bytes gauge'
union all
select format(
  'mlcore_table_index_bytes{tablespace="%s",table="%s"} %s',
  tablespace,
  table_name,
  index_bytes
)
from table_stats
union all select '# HELP mlcore_table_total_bytes PostgreSQL total bytes for MLCore tables including indexes.'
union all select '# TYPE mlcore_table_total_bytes gauge'
union all
select format(
  'mlcore_table_total_bytes{tablespace="%s",table="%s"} %s',
  tablespace,
  table_name,
  total_bytes
)
from table_stats
union all select '# HELP mlcore_table_estimated_rows PostgreSQL estimated rows for MLCore tables.'
union all select '# TYPE mlcore_table_estimated_rows gauge'
union all
select format(
  'mlcore_table_estimated_rows{tablespace="%s",table="%s"} %s',
  tablespace,
  table_name,
  estimated_rows
)
from table_stats
union all select '# HELP mlcore_tablespace_mlcore_total_bytes Total MLCore table bytes by tablespace.'
union all select '# TYPE mlcore_tablespace_mlcore_total_bytes gauge'
union all
select format(
  'mlcore_tablespace_mlcore_total_bytes{tablespace="%s"} %s',
  tablespace,
  total_bytes
)
from tablespace_totals
union all select '# HELP mlcore_tablespace_mlcore_estimated_rows Total estimated MLCore rows by tablespace.'
union all select '# TYPE mlcore_tablespace_mlcore_estimated_rows gauge'
union all
select format(
  'mlcore_tablespace_mlcore_estimated_rows{tablespace="%s"} %s',
  tablespace,
  estimated_rows
)
from tablespace_totals;
SQL
SCRIPT

mv "${tmp_path}" "${METRICS_PATH}"
echo "wrote ${METRICS_PATH}"
