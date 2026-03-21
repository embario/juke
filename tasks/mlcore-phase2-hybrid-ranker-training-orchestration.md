---
id: mlcore-phase2-hybrid-ranker-training-orchestration
title: ML Core Phase 2 - Hybrid ranker training, versioning, and scheduled refresh
status: ready
priority: p1
owner: unassigned
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - training
  - operations
complexity: 5
updated_at: 2026-03-19
---

## Goal

Implement an end-to-end, repeatable training pipeline for the hybrid model using the unified training corpus and existing MLCore governance/evaluation infrastructure.

## Scope

- Add dedicated trainer entrypoint for hybrid model fitting from feature corpus.
- Persist trainer run metadata with:
  - training set hash
  - split config
  - source version manifest snapshot
  - feature schema hash
- Add artifact registration to `mlcore_embedding_model` or a new hybrid model table if needed.
- Add model activation/promotion compatibility checks:
  - candidate metric improvement
  - license policy compliance
  - source-specific ablation thresholds
- Add scheduled retraining job and promotion workflow integration.
- Add rollback path to last-good model.

## Out Of Scope

- Product-level A/B serving code paths.
- Recommendation endpoint response formatting.

## Acceptance Criteria

- Running training from CLI creates a versioned model artifact with lineage.
- Training can be re-run with deterministic output for same dataset hash.
- Evaluation commands compare candidate hybrid model against metadata/cooccurrence/content baselines on the same shared eval dataset hash.
- Promotion API/commands can reference the hybrid model artifact and lineage row.
- Stale lineage is detected and logged (training-run timestamp, corpus hash mismatch).

## Execution Notes

### Proposed components

- `backend/mlcore/services/hybrid_training.py` (new): train + serialize + register.
- `backend/mlcore/tasks.py`:
  - `train_hybrid_ranker_task`
  - `refresh_hybrid_schedule_task`
- `backend/mlcore/management/commands/train_hybrid_ranker.py` (new)
- `backend/mlcore/services/promotion.py`: add hybrid candidate label coverage and model-specific gates.
- `backend/settings/base.py`: schedules/threshold defaults for hybrid training frequency.

### Suggested tests

- `tests/unit/test_hybrid_training.py`
- `tests/unit/test_hybrid_promotion_gate.py`
- `tests/unit/test_hybrid_retrain_reproducibility.py`

## Risks

- High coupling between feature store shape and model fit code.
- False-positive gains from unstable negative sampling or leakage.
- Operational cost of frequent retraining on large external datasets.

## Handoff

- Next: integrate results into [tasks/mlcore-phase3-hybrid-ranking-and-explainability.md](/Users/embario/Documents/juke/tasks/mlcore-phase3-hybrid-ranking-and-explainability.md) serving and explainability output.
- Blocker: none.

## Dependencies

- Must start after:
  - `mlcore-phase1c-hybrid-training-data-corpus`
  - `mlcore-phase1-eval-promotion-gates` (for gate schema compatibility and reporting contract).
- This task should be blocked until feature source ingestion is at least one complete cycle behind data freshness policy.
