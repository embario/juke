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
updated_at: 2026-03-06
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
