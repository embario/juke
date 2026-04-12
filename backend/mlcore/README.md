# MLCore (Phase 1) — Recommendation Baselines

This directory contains the model-training + scoring primitives used by the Juke recommendation engine.
It is intentionally lightweight and opinionated: two baseline rankers (metadata graph and co-occurrence)
and a small offline evaluation path that mirrors the serving logic.

## Purpose

ML engineers should use MLCore for:

- Building deterministic pairwise co-occurrence statistics from behavioral session data.
- Running offline evaluation over leave-one-out trials from historical behavior.
- Producing training run and evaluation artifacts for governance/profiling.
- Improving phase-1 baselines before content embedding models.

## Core concepts

### Track identity and canonical IDs
- MLCore uses canonical `UUID` `juke_id`s.
- Co-occurrence rows store ordered pairs `(item_a_juke_id, item_b_juke_id)` where
  `a < b` lexicographically.
- This ensures exactly one row per unordered pair.

### Models and artifacts
- `TrainingRun`: one trainer invocation (hashes + row counts + timestamp).
- `ItemCoOccurrence`: one row per canonical pair with `co_count` and `pmi_score`.
- `ModelEvaluation`: one row per `(candidate_label, metric_name, dataset_hash)`.
- `ModelPromotion`: current governance object for promotion checks.

## Behavioral input: baskets

Phase 1 reads track baskets from blended behavioral sources by default:

- internal `SearchHistoryResource`
- external `NormalizedInteraction` rows such as `listenbrainz`

- Default resource type: `track`
- Minimum basket size: `2`
- Splits are controlled by session id:
  - `train`: `session_id % 10 != 0`
  - `test`: `session_id % 10 == 0`
  - `all`: no split filter

For external normalized sources, split selection is deterministic via a hash of
`source_id:session_hint`, so train/test bucket assignment remains stable as rows grow.

## Train co-occurrence

### Train from blended behavioral sources (default)

```python
from mlcore.services.cooccurrence import train_cooccurrence

result = train_cooccurrence()  # defaults: split='train', split_buckets=10
print(result.training_run_id)
print(result.pairs_written, result.baskets_processed)
```

### Train from the command line

```bash
# default: blended search_history + listenbrainz, train split
docker compose -f docker-compose.yml exec backend python manage.py train_cooccurrence

# train from all blended baskets
docker compose -f docker-compose.yml exec backend python manage.py train_cooccurrence --split all

# force a single source
docker compose -f docker-compose.yml exec backend python manage.py train_cooccurrence --split all --source listenbrainz
docker compose -f docker-compose.yml exec backend python manage.py train_cooccurrence --split all --source search_history

# explicit blended invocation
docker compose -f docker-compose.yml exec backend python manage.py train_cooccurrence \
  --source search_history \
  --source listenbrainz
```

### Train from explicit baskets

```python
from uuid import UUID
from mlcore.services.cooccurrence import train_cooccurrence

baskets = [
    [UUID('...'), UUID('...')],
    [UUID('...'), UUID('...'), UUID('...')],
]
result = train_cooccurrence(baskets=baskets, split='all')
```

### Notes

- `train_cooccurrence()` always creates a `TrainingRun` and writes to `ItemCoOccurrence`.
- Inserts are conflict-upserted on pair key, so reruns update existing rows deterministically.
- `training_hash` from the basket contents supports reproducibility checks.

## Celery task

A task wrapper is available for orchestration:

- `mlcore.tasks.train_cooccurrence_task`
- `mlcore.tasks.sync_listenbrainz_remote_task`
- `mlcore.tasks.import_listenbrainz_full_task`
- `mlcore.tasks.replay_listenbrainz_incremental_task`

`train_cooccurrence_task` accepts `split`, `split_buckets`, and `sources`.
By default it trains from blended `search_history` + `listenbrainz` sources.

## Offline evaluation

Run from the Django command line:

```bash
# all rankers (metadata + cooccurrence), blended behavioral sources by default
docker compose -f docker-compose.yml exec backend python manage.py evaluate_recommenders

# only cooccurrence, k=20
docker compose -f docker-compose.yml exec backend python manage.py evaluate_recommenders --ranker cooccurrence --k 20

# evaluate only listenbrainz-backed trials
docker compose -f docker-compose.yml exec backend python manage.py evaluate_recommenders \
  --ranker cooccurrence \
  --source listenbrainz \
  --no-persist
```

This command:

- Builds leave-one-out trials from baskets.
- Computes recall@K, nDCG@K, coverage, cold-start recall.
- Persists results in `mlcore_model_evaluation` unless `--no-persist` is passed.

## ListenBrainz operations

ListenBrainz import supports both manual file-based imports and scheduled remote
sync. The scheduled path discovers new releases from the official MetaBrainz FTP
index, downloads the `listenbrainz-listens-dump-*.tar.zst` artifacts into local
storage, and imports them through the same policy-gated pipeline used by manual
file imports. Supported input formats are plain JSON-lines files, `.gz`, `.tar`,
`.tar.gz`, `.tgz`, and `.tar.zst`.

### Environment knobs

- `MLCORE_LISTENBRAINZ_FULL_IMPORT_PATH`
- `MLCORE_LISTENBRAINZ_INCREMENTAL_IMPORT_PATH`
- `MLCORE_LISTENBRAINZ_FULL_SOURCE_VERSION`
- `MLCORE_LISTENBRAINZ_INCREMENTAL_SOURCE_VERSION`
- `MLCORE_LISTENBRAINZ_REMOTE_ROOT_URL`
- `MLCORE_LISTENBRAINZ_DOWNLOAD_DIR`
- `MLCORE_LISTENBRAINZ_REMOTE_TIMEOUT_SECONDS`
- `MLCORE_LISTENBRAINZ_REMOTE_SYNC_SCHEDULE_SECONDS`
- `MLCORE_LISTENBRAINZ_REMOTE_SYNC_MAX_INCREMENTALS_PER_RUN`
- `MLCORE_LISTENBRAINZ_MAX_MALFORMED_ROWS`
- `MLCORE_LISTENBRAINZ_USER_HASH_SALT`
- `MLCORE_LISTENBRAINZ_SESSION_WINDOW_SECONDS`

### Example `.env` values

```env
MLCORE_LISTENBRAINZ_FULL_IMPORT_PATH=/srv/juke-data/listenbrainz/fullexport-2026-03-22.tar.zst
MLCORE_LISTENBRAINZ_INCREMENTAL_IMPORT_PATH=/srv/juke-data/listenbrainz/incremental-2026-03-23.tar.gz
MLCORE_LISTENBRAINZ_FULL_SOURCE_VERSION=2026-03-22
MLCORE_LISTENBRAINZ_INCREMENTAL_SOURCE_VERSION=2026-03-23
MLCORE_LISTENBRAINZ_REMOTE_ROOT_URL=https://ftp.musicbrainz.org/pub/musicbrainz/listenbrainz/
MLCORE_LISTENBRAINZ_DOWNLOAD_DIR=/srv/data/listenbrainz
MLCORE_LISTENBRAINZ_REMOTE_TIMEOUT_SECONDS=60
MLCORE_LISTENBRAINZ_REMOTE_SYNC_SCHEDULE_SECONDS=86400
MLCORE_LISTENBRAINZ_REMOTE_SYNC_MAX_INCREMENTALS_PER_RUN=14
MLCORE_LISTENBRAINZ_MAX_MALFORMED_ROWS=0
MLCORE_LISTENBRAINZ_SESSION_WINDOW_SECONDS=1800
```

### Import commands

```bash
# run the full import task against configured env paths
docker compose -f docker-compose.yml exec backend python manage.py shell -c \
  "from mlcore.tasks import import_listenbrainz_full_task; print(import_listenbrainz_full_task.apply().get())"

# discover/download/import the latest full dump plus missing incrementals
docker compose -f docker-compose.yml exec backend python manage.py sync_listenbrainz_remote

# run the incremental replay task against configured env paths
docker compose -f docker-compose.yml exec backend python manage.py shell -c \
  "from mlcore.tasks import replay_listenbrainz_incremental_task; print(replay_listenbrainz_incremental_task.apply().get())"

# run a one-off import against an explicit file path
docker compose -f docker-compose.yml exec backend python manage.py shell -c \
  "from mlcore.ingestion.listenbrainz import import_listenbrainz_dump; \
print(import_listenbrainz_dump('/data/listenbrainz/sample.tar.gz', source_version='sample-2026-03-22', import_mode='full'))"
```

When the import runs through Celery, task progress is exposed through the
result backend with `state='PROGRESS'` and metadata including:

- `source_row_count`
- `imported_row_count`
- `duplicate_row_count`
- `canonicalized_row_count`
- `unresolved_row_count`
- `malformed_row_count`
- `last_origin`
- `last_line_number`

Example progress probe:

```bash
docker compose -f docker-compose.yml exec backend python manage.py shell -c \
  "from celery.result import AsyncResult; r=AsyncResult('<task-id>'); print(r.state); print(r.info)"
```

### Operator notes

- Scheduled sync runs through `mlcore.tasks.sync_listenbrainz_remote` once per
  `MLCORE_LISTENBRAINZ_REMOTE_SYNC_SCHEDULE_SECONDS` interval. It imports the
  latest full dump when a new one appears upstream, then replays only the
  missing incremental releases published after that full baseline.
- ListenBrainz is classified `production_approved` in `LicensePolicy`. It is
  eligible for production ML use as long as the privacy constraints from
  `docs/arch/MLCORE_DATASET_VIABILITY_ASSESSMENT.md` remain in place.
- Raw rows are immutable in `ListenBrainzRawListen`; rerunning the same dump creates a new `SourceIngestionRun` but suppresses duplicate event signatures.
- `NormalizedInteraction.track` may be null when MBID/Spotify fallback resolution fails. Those rows remain valuable for audit metrics but do not form baskets until resolved.
- Manual full/incremental import tasks remain available for one-off backfills and local testing against explicit files.

## Serving interfaces (integration)

Engine endpoints used by clients:

- `POST /engine/recommend/metadata`
- `POST /engine/recommend/cooccurrence`

Both support deterministic exclusion of seed items and share the same score logic used by offline rankers.

Scoring implementation is in
[`backend/recommender_engine/app/scorers.py`](/Users/embario/Documents/juke/backend/recommender_engine/app/scorers.py).

## Reproducibility and lineage

Use these fields when comparing experiments:

- `TrainingRun.training_hash`: hash of training baskets.
- `TrainingRun.source_row_count`: raw source rows consumed.
- `TrainingRun` foreign key on `ItemCoOccurrence`.
- `ModelEvaluation.dataset_hash`: hash of evaluation trials.

Always record all four artifacts when promoting a candidate.

## Useful files

- [`backend/mlcore/services/cooccurrence.py`](/Users/embario/Documents/juke/backend/mlcore/services/cooccurrence.py)
- [`backend/mlcore/services/evaluation.py`](/Users/embario/Documents/juke/backend/mlcore/services/evaluation.py)
- [`backend/mlcore/ingestion/listenbrainz.py`](/Users/embario/Documents/juke/backend/mlcore/ingestion/listenbrainz.py)
- [`backend/mlcore/management/commands/train_cooccurrence.py`](/Users/embario/Documents/juke/backend/mlcore/management/commands/train_cooccurrence.py)
- [`backend/mlcore/management/commands/evaluate_recommenders.py`](/Users/embario/Documents/juke/backend/mlcore/management/commands/evaluate_recommenders.py)
- [`backend/mlcore/models.py`](/Users/embario/Documents/juke/backend/mlcore/models.py)
- [`backend/mlcore/tasks.py`](/Users/embario/Documents/juke/backend/mlcore/tasks.py)

## Routine checks

From inside backend container:

```bash
docker compose -f docker-compose.yml exec backend python manage.py makemigrations --check --no-input
docker compose -f docker-compose.yml exec backend python manage.py test
```

Target these around any change to ranking, trainer, or evaluation behavior.
