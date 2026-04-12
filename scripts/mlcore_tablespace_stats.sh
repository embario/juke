#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-${REPO_ROOT}/docker-compose.yml}"
ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.env}"

compose_cmd=(docker compose -f "${COMPOSE_FILE}")
if [[ -f "${ENV_FILE}" ]]; then
    compose_cmd+=(--env-file "${ENV_FILE}")
fi

"${compose_cmd[@]}" exec -T db bash <<'SCRIPT'
set -euo pipefail

DB_NAME="${POSTGRES_NAME:-postgres}"
DB_USER="${POSTGRES_USER:-postgres}"

echo "== Tablespace Filesystems =="
psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" -At <<'SQL' | while IFS="|" read -r spcname location; do
with ts as (
  select
    spcname,
    case
      when spcname in ('pg_default', 'pg_global') then current_setting('data_directory')
      else nullif(pg_tablespace_location(oid), '')
    end as location
  from pg_tablespace
)
select spcname, location
from ts
order by spcname;
SQL
  echo
  echo "[$spcname] $location"
  df -h "$location" | sed "s/^/  /"
done

echo
echo "== MLCore Table Stats =="
psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" <<'SQL'
with table_stats as (
  select
    c.oid,
    c.relname as table_name,
    coalesce(ts.spcname, 'pg_default') as tablespace,
    pg_relation_size(c.oid) as table_bytes,
    pg_indexes_size(c.oid) as index_bytes,
    pg_total_relation_size(c.oid) as total_bytes,
    c.reltuples::bigint as estimated_rows
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
    sum(total_bytes) as tablespace_bytes
  from table_stats
  group by tablespace
)
select
  t.tablespace,
  t.table_name,
  t.estimated_rows,
  pg_size_pretty(t.table_bytes) as table_size,
  pg_size_pretty(t.index_bytes) as index_size,
  pg_size_pretty(t.total_bytes) as total_size,
  round(100.0 * t.total_bytes / nullif(tt.tablespace_bytes, 0), 2) as pct_of_mlcore_tablespace
from table_stats t
join tablespace_totals tt on tt.tablespace = t.tablespace
order by t.tablespace, t.total_bytes desc;
SQL

echo
echo "== MLCore Tablespace Totals =="
psql -v ON_ERROR_STOP=1 -U "$DB_USER" -d "$DB_NAME" <<'SQL'
with table_stats as (
  select
    coalesce(ts.spcname, 'pg_default') as tablespace,
    pg_total_relation_size(c.oid) as total_bytes
  from pg_class c
  join pg_namespace n on n.oid = c.relnamespace
  left join pg_tablespace ts on ts.oid = c.reltablespace
  where n.nspname = 'public'
    and c.relkind = 'r'
    and c.relname like 'mlcore_%'
)
select
  tablespace,
  pg_size_pretty(sum(total_bytes)) as mlcore_total_size
from table_stats
group by tablespace
order by sum(total_bytes) desc;
SQL

echo
echo "Note: estimated_rows comes from PostgreSQL statistics (fast, approximate)."
SCRIPT
