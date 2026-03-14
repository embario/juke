---
id: mlcore-cooccurrence-training-provenance
title: Co-occurrence training provenance — version the stats table and link eval to training runs
status: completed
priority: p2
owner: unassigned
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - data-lineage
complexity: 3
updated_at: 2026-03-14
---

## Goal

Make `ItemCoOccurrence` training runs versioned and linkable from `ModelEvaluation`,
so a promotion decision can answer "trained on what?" and a retrain doesn't silently
invalidate prior evaluation rows.

## Problem

Identified during ML Core Phase 1 Stage 4 (2026-03-06). The co-occurrence table is a
**mutable singleton** — `train_cooccurrence()` overwrites rows in place via
`bulk_create(update_conflicts=True)` (`mlcore/services/cooccurrence.py:158-163`).

Three consequences:

1. **No training provenance.** `ModelEvaluation.dataset_hash` identifies the *eval*
   LOO set. Nothing records which `SearchHistory` rows fed the trainer. The only
   breadcrumb is `ItemCoOccurrence.updated_at`, which tells you *when* but not *what*.

2. **Eval staleness is silent.** Evaluate `cooccurrence` today → retrain tomorrow with
   more sessions → yesterday's `ModelEvaluation` rows now describe a table state that
   no longer exists. No FK, no version stamp, no way to detect this.

3. **No train/test split.** Trainer (`baskets_from_search_history()`,
   `cooccurrence.py:50-87`) and evaluator (`build_loo_dataset()`, `evaluation.py:101-147`)
   both pull from the full `SearchHistoryResource` table at call time. We evaluate on
   the training set. Tolerable for Phase 1 plumbing; not for real promotion decisions.

The arch doc's provenance story (`mlcore_embedding_model` registry, arch §5.4 line 223)
was designed for embedding models with checkpoint artifacts. Cooccurrence doesn't fit —
there's no weight file to version, just rows.

## Scope

- **`TrainingRun` model** (new): one row per `train_cooccurrence()` invocation.
  Fields: `id` (UUID PK), `ranker_label`, `training_hash` (SHA256 over sorted basket
  contents — same scheme as `build_loo_dataset()`), `baskets_processed`, `items_seen`,
  `pairs_written`, `source_row_count` (snapshot of `SearchHistoryResource.count()` at
  train time), `created_at`.
- **`ItemCoOccurrence.training_run`** FK → `TrainingRun`. Rows get stamped with the run
  that wrote them. Old rows from prior runs either get the new stamp (current overwrite
  semantics) or get deleted if they're no longer in the fresh basket set — decide which.
- **`ModelEvaluation.training_run`** nullable FK. `CoOccurrenceRanker` exposes its
  current `training_run` via a property; `evaluate_ranker()` picks it up and
  `persist_evaluation()` stores it. Embedding-model evals leave it null (they use
  `model_id` instead).
- **Train/test split**: `baskets_from_search_history()` grows a `split` parameter
  (`'train'` / `'test'` / `'all'`). Deterministic split by hashing `search_history_id`
  mod some bucket count. Trainer uses `'train'`, evaluator uses `'test'`.
- Update `mlcore/management/commands/evaluate_recommenders.py` to refuse evaluation
  of `cooccurrence` if no `TrainingRun` exists, or warn if the newest run's
  `training_hash` doesn't match current `SearchHistoryResource` state.

## Out Of Scope

- Retroactive versioning of the current Phase 1 table (it's throwaway bootstrap data).
- Multi-version cooccurrence tables coexisting (keep the singleton-overwrite model;
  just stamp which run produced the current rows).
- Generalising `TrainingRun` to cover embedding training — that's what
  `mlcore_embedding_model` is for. This is the behavioral-stats equivalent.

## Acceptance Criteria

- A `ModelEvaluation` row for `candidate_label='cooccurrence'` can be joined to the
  `TrainingRun` that produced the `ItemCoOccurrence` rows it ranked over.
- Retraining after an eval run is detectable: query
  `ModelEvaluation.training_run.created_at < ItemCoOccurrence.training_run.created_at`.
- Train and eval basket sets are disjoint when `split` is used.
- `training_hash` is stable across runs with identical input (same determinism
  guarantees as `dataset_hash`).

## Execution Notes

- Key files:
  - `backend/mlcore/models.py` — add `TrainingRun`, add FK on `ItemCoOccurrence` + `ModelEvaluation`
  - `backend/mlcore/services/cooccurrence.py` — compute `training_hash`, create `TrainingRun`, stamp rows, add `split` param
  - `backend/mlcore/services/evaluation.py` — `CoOccurrenceRanker` exposes `training_run`; `persist_evaluation()` stores it; `build_loo_dataset()` accepts `split`
  - `backend/mlcore/management/commands/evaluate_recommenders.py` — staleness check
- Commands:
  - `docker compose exec backend python manage.py makemigrations mlcore`
  - `docker compose exec backend python manage.py test tests.unit.test_cooccurrence_trainer tests.unit.test_evaluation`
- Risks:
  - Deterministic split by `search_history_id` hash means the split shifts as new
    sessions arrive (a session that was `'test'` yesterday might be `'train'` today
    if the bucket boundary moves). Fix: hash the ID directly, don't mod by count.
  - Adding a NOT NULL FK to `ItemCoOccurrence` needs a data migration for existing
    rows. Either make it nullable or truncate + retrain on deploy.

## Handoff

- Completed:
  - AC3 implemented: `train_cooccurrence()` defaults to `split='train'` and now excludes `split='test'` buckets by default.
  - `TrainingRun` model and migration for `mlcore_training_run`.
  - `ItemCoOccurrence` and `ModelEvaluation` now carry nullable FK links to `TrainingRun`.
  - `train_cooccurrence()` computes/stores `training_hash` and stamps rows with `training_run`.
  - `baskets_from_search_history()` and `build_loo_dataset()` support `split` (`train`/`test`/`all`) plus `split_buckets`.
  - `evaluate_recommenders` warns when `cooccurrence` has no training run or when train hash is stale.
  - offline evaluation can pass and persist `cooccurrence` training run context.
  - Added/updated MLCore unit tests for split handling and training lineage fields.
  - Added `backend/mlcore/migrations/0003_mlcore_trainingrun_lineage.py`.
  - Gap identified and scoped during Phase 1 Stage 4 review.
- Next:
  - Prioritise against `musicprofile-favorites-resolvable-identity` — both expand
    the eval harness's input surface. Doing this one first means the split logic
    is in place before favorites add a second basket source.
- Blockers:
  - Local commit is blocked by environment hook dependencies (`docker compose` unavailable during pre-commit backend ruff checks). Code is staged and awaiting final hook-pass commit path.
