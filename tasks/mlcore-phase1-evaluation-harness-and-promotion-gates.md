---
id: mlcore-phase1-eval-promotion-gates
title: ML Core Phase 1 - Offline evaluation harness and model promotion gates
status: review
priority: p1
owner: codex
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - evaluation
complexity: 3
updated_at: 2026-03-06
---

## Goal

Create repeatable offline evaluation and enforce promotion thresholds before model activation.

## Scope

- Implement offline evaluator producing `Recall@10`, `nDCG@10`, coverage, and cold-start slice metrics.
- Persist metrics in `mlcore_model_evaluation`.
- Implement promotion gate checks:
- `nDCG@10` >= +5% relative
- `Recall@10` >= +3% relative
- cold-start regression <= 2%
- coverage >= 30%
- Add manual promotion approval workflow (project owner).

## Out Of Scope

- ANN index tuning.
- Real-time feature store or online learning.

## Acceptance Criteria

- Evaluation run is reproducible from dataset hash and model ID.
- Promotion is blocked when thresholds fail.
- Promotion path records approver identity and timestamp.

## Execution Notes

- Key files:
- `/Users/embario/Documents/juke/backend/mlcore/services/evaluation.py`
- `/Users/embario/Documents/juke/backend/mlcore/models.py`
- `/Users/embario/Documents/juke/backend/mlcore/management/commands/*` (new)
- Commands:
- `docker compose exec backend python manage.py evaluate_recommenders`
- `docker compose exec backend python manage.py test`
- Risks:
- Metric proxies may drift from product relevance if dataset slices are unbalanced.

## Handoff

- Completed:
  - **Evaluator** — `backend/mlcore/services/evaluation.py` (364 lines). Three layers: pure metric functions (`recall_at_k`, `ndcg_at_k`, `coverage` — unit-testable with no DB), `build_loo_dataset()` (leave-one-out trial builder), `run_offline_evaluation()` (runs rankers, aggregates, optionally persists). Metric name constants (`METRIC_RECALL` etc.) are exported — promotion gates join on them, so they're the contract.
  - **Dataset hash** — SHA256 over **sorted** `seeds|held_out` trial lines. Stable across basket permutations, basket-list ordering, and dict-iteration order. This is how you prove two eval runs compared the same ground truth. Determinism covered by `test_evaluation.py::test_hash_stable_across_*` + `test_mlcore_pipeline.py::test_06`.
  - **LOO source = SearchHistory only** — see `baskets_from_search_history()`. `MusicProfile.favorite_tracks` is *not* in scope because it stores song-name strings, not IDs — documented in `tasks/musicprofile-favorites-resolvable-identity.md`. The evaluator module docstring points there.
  - **Cold-start slice** — a trial is `is_cold=True` if the held-out track appears in ≤2 baskets. `METRIC_COLD_RECALL` is recall@10 restricted to that slice. Falls back to `0.0` if the slice is empty (no division by zero).
  - **Promotion gates** — `backend/mlcore/services/promotion.py` (268 lines). Four gates wired to the `JUKE_PROMOTION_GATE_*` settings from `settings/base.py:357-360`. Gate functions **never raise**: missing `ModelEvaluation` rows = failed `GateCheck` with a readable `message`, not an exception. `gate_results` JSON on `ModelPromotion` records every check, pass or fail, so you can see *which* gate blocked after the fact.
    - `baseline == 0.0` policy: any positive candidate clears a lift gate (reported as `lift=inf`); `0.0 vs 0.0` fails. No division-by-zero path.
    - Lift gates use `>=`; IEEE-754 rounds `(0.42-0.40)/0.40` to `0.04999...` which correctly **fails** a 5% gate. This is the conservative direction. Don't "fix" it. See the comment block in `test_promotion.py` around line 70 — boundary tests use exactly-representable floats (`0.50 → 0.53125`, lift = 1/16).
  - **Approval workflow** — `request_promotion()` runs gates → writes `pending` or `blocked`; `approve_promotion()` requires `is_staff`, **re-runs gates** against current `ModelEvaluation` state (race guard: if a regressed eval row landed between request and approval, the promotion flips to `blocked` instead of silently approving stale results — `test_promotion.py::test_gates_rechecked_at_approval_time`), stamps `approved_by` + `approved_at`. `reject_promotion()` for the manual no.
  - **Admin** — `backend/mlcore/admin.py`. Both `ModelEvaluation` and `ModelPromotion` are **fully read-only** (`has_add_permission`/`has_change_permission` return `False`; all fields in `readonly_fields`). Status transitions go through the `approve_selected` / `reject_selected` admin actions, which call the service — so gates can't be bypassed by editing `status` in the form.
  - **Commands** — `evaluate_recommenders` (run eval, `--no-persist` for dry runs); `promote_recommender` (three modes: dry-run needs `--dataset-hash`; `--request` writes the row; `--approve --approver <user>` does the full flow — validates approver exists **before** touching the DB).
  - **Tests** — `test_evaluation.py` (50), `test_promotion.py` (35), `test_mlcore_pipeline.py` (7 — full SearchHistory→train→eval→promote loop against a real fixture where cooccurrence *measurably* beats metadata: `cold_recall` 0.0 vs 1.0), `test_mlcore_coverage_gaps.py` (21 — management commands via `call_command`, Celery task via `.apply()`, batch-size chunking, M2M cross-products).
- Next:
  - The eval harness reads all of `SearchHistory` as both training *and* eval data. There's no train/test split. For Phase 1's "does the pipeline cohere" goal that's fine — for Phase 2's "is this model actually better" you need the deterministic split designed in `tasks/mlcore-cooccurrence-training-provenance.md` (hash `search_history_id` into buckets; don't mod by count or the split shifts as data grows).
  - `ModelEvaluation.model_id` is populated but nothing enforces that the `ItemCoOccurrence` table you're evaluating matches any particular training run. Same follow-up task.
- Blockers: none.
