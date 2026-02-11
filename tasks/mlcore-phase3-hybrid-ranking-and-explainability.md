---
id: mlcore-phase3-hybrid-ranking
title: ML Core Phase 3 - Hybrid ranking and explainable recommendation outputs
status: ready
priority: p1
owner: unassigned
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - ranking
complexity: 5
updated_at: 2026-02-11
---

## Goal

Implement production hybrid ranking that blends content, metadata, and cooccurrence with MMR diversification and explainable scores.

## Scope

- Add `POST /engine/recommend` hybrid endpoint.
- Implement weighted blend from active `mlcore_ranking_weight_config` (DB only).
- Implement MMR diversification with configurable lambda.
- Return explainability fields per item:
- `content_score`
- `metadata_score`
- `cooccurrence_score`
- `final_score`
- `model_version`
- `weight_config_id`

## Out Of Scope

- New client UI to visualize explainability.
- Online bandit/reinforcement updates.

## Acceptance Criteria

- Hybrid endpoint outperforms each standalone signal model in offline evaluation.
- Cold-start results improve vs cooccurrence-only baseline.
- API contract includes explainability fields for every recommendation item.
- Per-request weight overrides are rejected/ignored by design.

## Execution Notes

- Key files:
- `/Users/embario/Documents/juke/backend/recommender_engine/app/main.py`
- `/Users/embario/Documents/juke/backend/recommender/serializers.py`
- `/Users/embario/Documents/juke/backend/recommender/views.py`
- `/Users/embario/Documents/juke/backend/mlcore/models.py`
- Commands:
- `docker compose exec backend python manage.py evaluate_recommenders`
- `docker compose exec backend python manage.py test`
- Risks:
- Weight miscalibration can collapse diversity or overfit one signal.

## Handoff

- Completed:
- Next:
- Blockers:
