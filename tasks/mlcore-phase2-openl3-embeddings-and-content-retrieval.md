---
id: mlcore-phase2-openl3-content
title: ML Core Phase 2 - OpenL3 embeddings and content retrieval via pgvector
status: ready
priority: p1
owner: unassigned
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - embeddings
complexity: 5
updated_at: 2026-02-11
---

## Goal

Ship content-based recommendations using OpenL3 embeddings stored in pgvector with IVFFlat retrieval.

## Scope

- Add `mlcore_embedding_model` and `mlcore_track_embedding` model registry/storage.
- Implement resumable OpenL3 extraction worker (windowing, pooling, idempotent upsert).
- Add `POST /engine/recommend/content` using active model and IVFFlat ANN.
- Enforce manifest license policy during extraction.
- Keep default `limit=10` and meet P95 <= 150ms target.

## Out Of Scope

- Hybrid blending with metadata/cooccurrence.
- UI changes consuming explainability fields.

## Acceptance Criteria

- OpenL3 embedding pipeline processes licensed corpus rows only.
- Active model switch is DB-driven without redeploy.
- Content endpoint returns deterministic top-K with ID exclusions.
- Performance benchmark demonstrates P95 <= 150ms for default request profile.

## Execution Notes

- Key files:
- `/Users/embario/Documents/juke/backend/mlcore/services/embedding_extract.py` (new)
- `/Users/embario/Documents/juke/backend/recommender_engine/app/main.py`
- `/Users/embario/Documents/juke/backend/mlcore/models.py`
- `/Users/embario/Documents/juke/docker-compose.yml`
- Commands:
- `docker compose exec backend python manage.py test`
- `docker compose exec backend python manage.py benchmark_retrieval`
- Risks:
- IVFFlat tuning (`lists`, `probes`) may need iteration for recall/latency balance.
- OpenL3 extraction throughput on limited hardware.

## Handoff

- Completed:
- Next:
- Blockers:
