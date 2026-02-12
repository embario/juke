---
id: mlcore-phase1-metadata-cooccurrence
title: ML Core Phase 1 - Metadata and cooccurrence recommendation baselines
status: ready
priority: p1
owner: unassigned
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - recommender
complexity: 5
updated_at: 2026-02-11
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

## Handoff

- Completed:
- Next:
- Blockers:
