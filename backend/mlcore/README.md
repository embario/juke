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

Phase 1 reads track baskets from `SearchHistoryResource`.

- Default resource type: `track`
- Minimum basket size: `2`
- Splits are controlled by session id:
  - `train`: `session_id % 10 != 0`
  - `test`: `session_id % 10 == 0`
  - `all`: no split filter

## Train co-occurrence

### Train from search history (default)

```python
from mlcore.services.cooccurrence import train_cooccurrence

result = train_cooccurrence()  # defaults: split='train', split_buckets=10
print(result.training_run_id)
print(result.pairs_written, result.baskets_processed)
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

It calls `train_cooccurrence()` and returns a dict with `pairs_written`, `baskets_processed`, `baskets_skipped`, `items_seen`.

## Offline evaluation

Run from the Django command line:

```bash
# all rankers (metadata + cooccurrence)
docker compose -f docker-compose.yml exec backend python manage.py evaluate_recommenders

# only cooccurrence, k=20
docker compose -f docker-compose.yml exec backend python manage.py evaluate_recommenders --ranker cooccurrence --k 20
```

This command:

- Builds leave-one-out trials from baskets.
- Computes recall@K, nDCG@K, coverage, cold-start recall.
- Persists results in `mlcore_model_evaluation` unless `--no-persist` is passed.

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
