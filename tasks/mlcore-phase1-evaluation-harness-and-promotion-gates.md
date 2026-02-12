---
id: mlcore-phase1-eval-promotion-gates
title: ML Core Phase 1 - Offline evaluation harness and model promotion gates
status: ready
priority: p1
owner: unassigned
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - evaluation
complexity: 3
updated_at: 2026-02-11
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
- Next:
- Blockers:
