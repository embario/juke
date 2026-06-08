#!/usr/bin/env bash
set -euo pipefail
umask 022

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
COMPOSE_FILE="${COMPOSE_FILE:-${REPO_ROOT}/docker-compose.yml}"
ENV_FILE="${ENV_FILE:-${REPO_ROOT}/.env}"
METRICS_PATH="${1:-${JUKE_HOST_NODE_EXPORTER_TEXTFILE_PATH:-/srv/monitoring/node-exporter/textfile}/mlcore_evaluation_history.prom}"

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
with evals as (
  select
    candidate_label,
    dataset_hash,
    coalesce(training_run_id::text, '') as training_run_id,
    coalesce(evaluation_started_at, max(created_at) - make_interval(secs => max(evaluation_elapsed_seconds))) as started_at,
    max(created_at) as completed_at,
    max(n_baskets) as n_baskets,
    max(n_trials) as n_trials,
    max(n_cold_trials) as n_cold_trials,
    max(evaluation_elapsed_seconds) as elapsed_seconds,
    max(evaluation_trials_per_second) as trials_per_second
  from mlcore_model_evaluation
  group by candidate_label, dataset_hash, training_run_id, evaluation_started_at
),
metrics as (
  select
    candidate_label,
    dataset_hash,
    coalesce(training_run_id::text, '') as training_run_id,
    metric_name,
    max(metric_value) as metric_value
  from mlcore_model_evaluation
  group by candidate_label, dataset_hash, training_run_id, metric_name
),
labels as (
  select
    candidate_label,
    dataset_hash,
    training_run_id,
    coalesce(to_char(started_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"'), '') as started_at_label,
    to_char(completed_at at time zone 'UTC', 'YYYY-MM-DD"T"HH24:MI:SS"Z"') as completed_at_label,
    coalesce(extract(epoch from started_at), 0) as started_at_epoch,
    extract(epoch from completed_at) as completed_at_epoch,
    n_baskets,
    n_trials,
    n_cold_trials,
    coalesce(elapsed_seconds, 0) as elapsed_seconds,
    coalesce(trials_per_second, 0) as trials_per_second
  from evals
)
select '# HELP mlcore_evaluation_result_info Completed evaluation metadata.'
union all select '# TYPE mlcore_evaluation_result_info gauge'
union all
select format(
  'mlcore_evaluation_result_info{candidate_label="%s",training_run_id="%s",dataset_hash="%s",started_at="%s",completed_at="%s",n_baskets="%s"} 1',
  candidate_label,
  training_run_id,
  dataset_hash,
  started_at_label,
  completed_at_label,
  n_baskets
)
from labels
union all select '# HELP mlcore_evaluation_result_started_at_seconds Completed evaluation start timestamp.'
union all select '# TYPE mlcore_evaluation_result_started_at_seconds gauge'
union all
select format(
  'mlcore_evaluation_result_started_at_seconds{candidate_label="%s",training_run_id="%s",dataset_hash="%s",started_at="%s",completed_at="%s"} %s',
  candidate_label,
  training_run_id,
  dataset_hash,
  started_at_label,
  completed_at_label,
  started_at_epoch
)
from labels
union all select '# HELP mlcore_evaluation_result_completed_at_seconds Completed evaluation completion timestamp.'
union all select '# TYPE mlcore_evaluation_result_completed_at_seconds gauge'
union all
select format(
  'mlcore_evaluation_result_completed_at_seconds{candidate_label="%s",training_run_id="%s",dataset_hash="%s",started_at="%s",completed_at="%s"} %s',
  candidate_label,
  training_run_id,
  dataset_hash,
  started_at_label,
  completed_at_label,
  completed_at_epoch
)
from labels
union all select '# HELP mlcore_evaluation_result_baskets Completed evaluation basket counts.'
union all select '# TYPE mlcore_evaluation_result_baskets gauge'
union all
select format(
  'mlcore_evaluation_result_baskets{candidate_label="%s",training_run_id="%s",dataset_hash="%s",started_at="%s",completed_at="%s"} %s',
  candidate_label,
  training_run_id,
  dataset_hash,
  started_at_label,
  completed_at_label,
  n_baskets
)
from labels
union all select '# HELP mlcore_evaluation_result_trials Completed evaluation trial counts.'
union all select '# TYPE mlcore_evaluation_result_trials gauge'
union all
select format(
  'mlcore_evaluation_result_trials{candidate_label="%s",training_run_id="%s",dataset_hash="%s",started_at="%s",completed_at="%s",slice="all"} %s',
  candidate_label,
  training_run_id,
  dataset_hash,
  started_at_label,
  completed_at_label,
  n_trials
)
from labels
union all
select format(
  'mlcore_evaluation_result_trials{candidate_label="%s",training_run_id="%s",dataset_hash="%s",started_at="%s",completed_at="%s",slice="cold"} %s',
  candidate_label,
  training_run_id,
  dataset_hash,
  started_at_label,
  completed_at_label,
  n_cold_trials
)
from labels
union all select '# HELP mlcore_evaluation_result_elapsed_seconds Completed evaluation runtime seconds.'
union all select '# TYPE mlcore_evaluation_result_elapsed_seconds gauge'
union all
select format(
  'mlcore_evaluation_result_elapsed_seconds{candidate_label="%s",training_run_id="%s",dataset_hash="%s",started_at="%s",completed_at="%s"} %s',
  candidate_label,
  training_run_id,
  dataset_hash,
  started_at_label,
  completed_at_label,
  elapsed_seconds
)
from labels
union all select '# HELP mlcore_evaluation_result_trials_per_second Completed evaluation throughput.'
union all select '# TYPE mlcore_evaluation_result_trials_per_second gauge'
union all
select format(
  'mlcore_evaluation_result_trials_per_second{candidate_label="%s",training_run_id="%s",dataset_hash="%s",started_at="%s",completed_at="%s"} %s',
  candidate_label,
  training_run_id,
  dataset_hash,
  started_at_label,
  completed_at_label,
  trials_per_second
)
from labels
union all select '# HELP mlcore_evaluation_result_metric Completed evaluation result metrics.'
union all select '# TYPE mlcore_evaluation_result_metric gauge'
union all
select format(
  'mlcore_evaluation_result_metric{candidate_label="%s",training_run_id="%s",dataset_hash="%s",started_at="%s",completed_at="%s",metric="%s"} %s',
  m.candidate_label,
  m.training_run_id,
  m.dataset_hash,
  l.started_at_label,
  l.completed_at_label,
  m.metric_name,
  m.metric_value
)
from metrics m
join labels l
  on l.candidate_label = m.candidate_label
 and l.dataset_hash = m.dataset_hash
 and l.training_run_id = m.training_run_id;
SQL
SCRIPT

mv "${tmp_path}" "${METRICS_PATH}"
echo "wrote ${METRICS_PATH}"
