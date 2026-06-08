---
id: mlcore-phase1-metadata-cooccurrence
title: ML Core Phase 1 - Metadata and cooccurrence recommendation baselines
status: review
priority: p1
owner: codex
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - recommender
complexity: 5
updated_at: 2026-05-28
---

## Goal

Deliver production-usable non-embedding baselines for metadata graph and cooccurrence recommendations in the FastAPI engine.

## Scope

- Add endpoint `POST /engine/recommend/metadata`.
- Add endpoint `POST /engine/recommend/cooccurrence`.
- Implement metadata scoring rules (artist/release/tag/work relation).
- Create `mlcore_item_cooccurrence` and training pipeline from open behavioral data.
- Enforce canonical ID seeds (`juke_id`) and ID-based exclusion.

## Out Of Scope

- Hybrid blending and MMR.
- Content embedding ANN retrieval.

## Acceptance Criteria

- Both endpoints return ranked lists with deterministic exclusion behavior.
- Cooccurrence trainer writes stable PMI/co-count rows.
- Endpoint behavior is covered with unit/integration tests.
- Latency remains within service SLO for default `limit=10`.

## Execution Notes

- Key files:
- `/Users/embario/Documents/juke/backend/recommender_engine/app/main.py`
- `/Users/embario/Documents/juke/backend/mlcore/models.py`
- `/Users/embario/Documents/juke/backend/mlcore/services/cooccurrence.py`
- `/Users/embario/Documents/juke/backend/mlcore/tasks.py`
- Commands:
- `docker compose exec backend python manage.py test`
- `docker compose exec backend ruff check .`
- Risks:
- Sparse cooccurrence coverage for niche items.
- Source data normalization quality impacts PMI scores.
- Arch §3.2 lists "conflicting rights annotations" as a fail-closed rejection trigger, but the Phase 0 `CorpusManifest` schema (one `license` + one `allowed_envs` per row) has no single-row field where a conflict can live. Interpretation: this is a cross-row reconciliation check at ingestion time — reject or flag when the same `checksum` appears under multiple `source` values with disagreeing `allowed_envs`/`license`. The Phase 0 `LicensePolicy.evaluate()` does not cover this; the training pipeline here must add the check before feeding `eligible_queryset()` output to the trainer.

## Handoff

- Completed:
  - **`ItemCoOccurrence` model** — `backend/mlcore/models.py`. Canonical `(item_a_juke_id, item_b_juke_id)` pair, lex-ordered (a < b), `unique_together` on the pair. Stores raw `co_count` + unsmoothed `pmi_score`. Migration `mlcore/0002`.
  - **Trainer** — `backend/mlcore/services/cooccurrence.py` (169 lines). `train_cooccurrence()` reads `SearchHistoryResource` baskets, counts pairs, computes PMI as `log2(N * co / (n_a * n_b))`, writes via `bulk_create(update_conflicts=True)` in `WRITE_BATCH_SIZE` chunks. Idempotent: rerunning on identical input produces identical rows — verified by `test_mlcore_pipeline.py::test_06_idempotent_retrain_same_eval_same_hash`.
  - **Celery task** — `backend/mlcore/tasks.py::train_cooccurrence_task`. Thin wrapper, returns the `TrainingResult` as a dict for the results backend.
  - **Engine endpoints** — `backend/recommender_engine/app/main.py` + `scorers.py` (149 lines). `POST /engine/recommend/metadata` and `POST /engine/recommend/cooccurrence`. Scoring logic lives in `scorers.py`, pure-stdlib (no Django, no psycopg imports) so the Django test runner imports it directly — see `tests/unit/test_engine_scorers.py`. The engine's raw SQL and the Django test harness call the **same** `score_metadata()` / `score_cooccurrence()` functions, so test parity with production is structural, not hoped-for.
  - **ORM mirror adapters** — `backend/mlcore/services/evaluation.py::MetadataRanker` / `CoOccurrenceRanker`. These replicate the engine's SQL joins in ORM so `run_offline_evaluation()` can run in the Django test DB without the engine container up. `_track_feature_rows()` deliberately emits the same cross-product rows the engine's `LEFT JOIN` produces (one row per artist×genre) — covered by `test_mlcore_coverage_gaps.py::TrackFeatureRowsM2MTests`.
  - **Tests** — 155 Phase-1 tests across `test_cooccurrence_trainer.py`, `test_engine_scorers.py`, `test_evaluation.py`, `test_promotion.py`, `test_mlcore_pipeline.py`, `test_mlcore_coverage_gaps.py`. Full suite: 369 passing, ruff clean.
- Next:
  - **Training provenance** — `tasks/mlcore-cooccurrence-training-provenance.md` (ready, p2). `ItemCoOccurrence` is a mutable singleton right now; a retrain overwrites it in place with no version link to the `ModelEvaluation` rows that were computed against it. The idempotency test guards against drift but doesn't give you "which training run produced this eval." Needs a `TrainingRun` model + FK before Phase 2.
  - **Feed `MusicProfile.favorite_tracks` into baskets** — `tasks/musicprofile-favorites-resolvable-identity.md` (blocked, p2). Trainer currently reads `SearchHistoryResource` only because `favorite_tracks` stores name strings, not resolvable IDs. Once that task lands, `baskets_from_search_history()` needs a sibling that emits favorites-baskets.
  - **Conflicting-rights check** (Risks above) — **not addressed** in Phase 1. The cross-row `CorpusManifest` checksum reconciliation matters for the *audio corpus* (Phase 2 OpenL3 ingestion), not for behavioral `SearchHistory` data which has no `CorpusManifest` gate. Carry this risk forward to `mlcore-phase2-openl3-embeddings-and-content-retrieval.md`.
  - **PMI smoothing** — deferred. Unsmoothed PMI overweights rare pairs. Fine for a baseline; revisit if cooccurrence wins promotion on real data and the long-tail recommendations look noisy.
- Blockers: none.

## Current Operational Handoff - 2026-05-28

- The completed ListenBrainz hot dataset is now being used for full-scale cooccurrence training rather than only test-scale `SearchHistoryResource` baskets.
- Uncommitted implementation in `backend/mlcore/services/cooccurrence.py` adds a ListenBrainz-only SQL training path with:
  - deterministic training hash tied to latest successful ListenBrainz ingestion state
  - 128 pair buckets
  - durable bucket progress rows in `mlcore_cooccurrence_training_bucket`
  - durable basket/session/pair staging tables
  - `--resume-run-id`, `--start-bucket`, and `--resume` support in `train_cooccurrence`
- The Neptune database has migrations through `mlcore.0018_trim_cooccurrence_staging_fk_indexes` applied.
- Latest observed full-scale run:
  - `TrainingRun.id=157bbf43-e842-46da-9f8a-d627d798044d`
  - created `2026-04-25T22:52:15Z`
  - `baskets_processed=235,951,375`
  - `items_seen=103,823,472`
  - `source_row_count=1,226,175,648`
  - `pairs_written=1,703,139,363`
  - bucket metadata: 116 `succeeded`, 12 `assumed_succeeded`
  - staging tables are empty after merge
  - `mlcore_item_cooccurrence` is about `284 GB` by PostgreSQL relation metadata
- Remaining before calling this Phase 1 path fully validated:
  - run a fresh full ListenBrainz-only cooccurrence training job from the current `mlcore_listenbrainz_session_track` snapshot now that incremental sync has been paused
  - run/evaluate the recommender candidates against the new cooccurrence training run
  - decide whether the 12 `assumed_succeeded` buckets are acceptable operationally or whether a clean 128/128 bucket run is required before promotion
  - update PR/issue linkage when this work is published
- Verification on 2026-05-28:
  - `docker compose exec backend python manage.py test tests.unit.test_listenbrainz_source_sync`
  - `docker compose exec backend python manage.py test tests.unit.test_cooccurrence_trainer`
- Operational setup for the next cooccurrence run:
  - incremental ListenBrainz sync has been intentionally paused
  - no Celery tasks are active and Redis `mlcore` queue length is `0`
  - worker consumption of the `mlcore` queue is disabled via `celery control cancel_consumer mlcore`
  - the current latest successful ListenBrainz source version remains `listenbrainz-dump-2501-20260422-000004-incremental`
  - recommended clean training command:
    `docker compose exec backend python manage.py train_cooccurrence --source listenbrainz --split train --split-buckets 10`
  - do not resume the older `TrainingRun.id=157bbf43-e842-46da-9f8a-d627d798044d` if the goal is a clean/current 128-bucket result
  - after training/evaluation, re-enable queued MLCore work with `docker compose exec worker celery -A settings.celery control add_consumer mlcore`

## Current Operational Handoff - 2026-05-30

- Resumed cooccurrence validation work on Neptune.
- Brought up only `db`, `redis`, and `backend`; intentionally did not start `worker` or `beat` so queued MLCore sync work cannot consume while the clean training run is active.
- Redis `mlcore` queue length is `3`; all three queued messages are `mlcore.tasks.sync_listenbrainz_remote`.
- Confirmed the latest pre-existing cooccurrence run is still `157bbf43-e842-46da-9f8a-d627d798044d` with 116 `succeeded` buckets and 12 `assumed_succeeded` buckets.
- Confirmed no persisted `ModelEvaluation` rows exist yet for `candidate_label='cooccurrence'`.
- Confirmed staging tables are empty by relation metadata and `mlcore_item_cooccurrence` remains about `284 GB`.
- Started a clean/current ListenBrainz-only training run as a one-off Compose container, not through Celery:
  - container: `juke-cooccurrence-train`
  - container id: `a027857d665e33dc9a024927e94fa2a1e8883dea508277e1d4ce07673b836595`
  - command: `docker compose run -d --name juke-cooccurrence-train backend python manage.py train_cooccurrence --source listenbrainz --split train --split-buckets 10`
  - new `TrainingRun.id=3c96bdf9-81c2-4b2a-8dfb-d1068e806fd8`
  - new training hash prefix: `2b21751dbd3e`
  - initial state: all 128 bucket rows `pending`; active DB query is inserting `mlcore_cooccurrence_training_basket`
- Next:
  - Monitor `juke-cooccurrence-train` and DB progress until basket/session staging finishes and bucket processing starts.
  - Do not start `worker`/`beat` or re-enable queued MLCore sync until training/evaluation is complete.
  - After training completes, evaluate with ListenBrainz-backed trials and decide promotion readiness.
- Added Neptune monitoring for the active training run:
  - textfile exporter script: `/srv/monitoring/scripts/mlcore-cooccurrence-training-export.sh`
  - textfile output: `/srv/monitoring/node-exporter/textfile/mlcore_cooccurrence_training.prom`
  - monitoring compose service: `mlcore-cooccurrence-textfile-exporter`
  - Grafana dashboard: `/srv/monitoring/grafana/dashboards/mlcore-cooccurrence-training.json`
  - dashboard URL: `http://100.110.159.98:3000/d/mlcore-cooccurrence-training/mlcore-cooccurrence-training`
  - verified `mlcore_cooccurrence_export_success=1` and `node_textfile_scrape_error=0`

## Current Operational Handoff - 2026-06-07

- Full cooccurrence training completed for `TrainingRun.id=3c96bdf9-81c2-4b2a-8dfb-d1068e806fd8`.
- Hot/cold storage split is active:
  - `mlcore_item_cooccurrence` remains in hot storage for ML serving.
  - `mlcore_listenbrainz_session_track` and cooccurrence staging tables are in cold storage.
- Added batched cooccurrence evaluation progress metrics:
  - textfile output: `/srv/monitoring/node-exporter/textfile/mlcore_evaluation.prom`
  - metric prefix: `mlcore_evaluation_*`
- Added MLCore table/tablespace textfile exporter:
  - script: `scripts/mlcore_tablespace_metrics.sh`
  - textfile output: `/srv/monitoring/node-exporter/textfile/mlcore_tablespace.prom`
  - metric prefixes: `mlcore_table_*`, `mlcore_tablespace_mlcore_*`
- Updated and deployed the repo Grafana dashboard source:
  - source: `o11y/mlcore-full-ingestion-dashboard.json`
  - live copy: `/srv/monitoring/grafana/dashboards/mlcore-full-ingestion-dashboard.json`
- Applied migration `mlcore.0023_model_evaluation_trial_counts` so future `ModelEvaluation` metric rows carry `n_trials` and `n_cold_trials`.
- Verification:
  - `docker compose exec -T backend python manage.py check`
  - `docker compose exec -T backend python manage.py test tests.unit.test_evaluation --keepdb`
- A persisted 10k-basket staged evaluation is running in the backend container:
  - backend PID: `511`
  - log: `/tmp/mlcore_eval_10k.log`
  - command: `python manage.py evaluate_recommenders --ranker cooccurrence --source listenbrainz --max-baskets 10000 --max-basket-items 25 --skip-hash-check --batch-size 5 --metrics-path /srv/monitoring/node-exporter/textfile/mlcore_evaluation.prom`
  - dataset hash: `cd5b3f81eed208e12b7c3f844b9c3b4e6078e5719c711781e970b7300e2ecdfe`
  - trials: `52,394`
  - cold trials: `51,953`
- Next:
  - Watch `mlcore_evaluation_progress_fraction`, `mlcore_evaluation_eta_seconds`, and `/tmp/mlcore_eval_10k.log`.
  - When complete, inspect the latest `mlcore_model_evaluation` rows grouped by `dataset_hash`.
  - If the 10k-basket result is stable and runtime is acceptable, launch a larger staged eval with the same `--batch-size 5` and `--max-basket-items 25` settings.
