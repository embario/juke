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
updated_at: 2026-03-23
---

## Goal

Implement production hybrid ranking that blends content, metadata, and cooccurrence with MMR diversification and explainable scores.

## Scope

- Add `POST /engine/recommend` hybrid endpoint.
- Implement weighted blend from active `mlcore_ranking_weight_config` (DB only).
- Implement MMR diversification with configurable lambda.
- Ensure the hybrid serving path is rooted in MLCore / engine endpoints rather than extending the legacy `backend/recommender` API surface.
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
- The implementation does not introduce new dependencies on legacy `backend/recommender` views/serializers/services; any required serving/orchestration code is MLCore-owned or engine-owned and ready for Phase 4 removal of the old recommender surface.

## Execution Notes

- Key files:
- `backend/recommender_engine/app/main.py`
- `backend/settings/urls.py`
- `backend/mlcore/models.py`
- `backend/mlcore/services/evaluation.py`
- Commands:
- `docker compose exec backend python manage.py evaluate_recommenders`
- `docker compose exec backend python manage.py test`
- Risks:
- Weight miscalibration can collapse diversity or overfit one signal.
- Accidental reuse of legacy `backend/recommender` API code would make Phase 4 cutover materially harder.

## Handoff

- Completed:
- Next:
- Blockers:
