---
id: mlcore-phase4-hardening-cutover
title: ML Core Phase 4 - Hardening, model operations, cutover, and legacy ML removal
status: ready
priority: p1
owner: unassigned
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - operations
complexity: 4
updated_at: 2026-03-23
---

## Goal

Operationalize the new ML core with health monitoring, scheduled re-embedding, model rollback controls, and complete removal of deprecated ML code.

## Scope

- Add scheduled jobs for new/stale track re-embedding.
- Add model health metric collection and persistence.
- Implement known-good model activation rollback path.
- Document and automate promotion workflow (manual owner approval).
- Remove legacy hash-based ML code and obsolete tests.
- Remove leftover `backend/recommender` API/orchestration artifacts once MLCore/engine cutover is complete.
- Remove stale Celery jobs, routes, settings, compose wiring, and tests that exist only to support the deprecated recommender surface.

## Out Of Scope

- Multi-approver governance workflow.
- Advanced feature-store architecture.

## Acceptance Criteria

- Nightly re-embedding runs automatically and is observable.
- Health metrics are recorded and queryable.
- Rollback to prior known-good model is executable in under 1 minute.
- Legacy hash-token recommender code paths are deleted.
- No dead `recommender` API artifacts remain after cutover: remove unused URL includes, views, serializers, service adapters, and tests for `/api/v1/recommendations/`.
- Any remaining code under `backend/recommender/` is justified by active MLCore/engine data ownership; otherwise it is migrated or deleted before closeout.
- Celery task registration, Django `INSTALLED_APPS`, and compose/runtime wiring no longer reference deprecated recommender-only components.
- End-to-end regression tests pass on new architecture.

## Execution Notes

- Key files:
- `/Users/embario/Documents/juke/backend/recommender_engine/app/main.py`
- `/Users/embario/Documents/juke/backend/recommender/*`
- `/Users/embario/Documents/juke/backend/mlcore/tasks.py`
- `/Users/embario/Documents/juke/backend/mlcore/models.py`
- `/Users/embario/Documents/juke/backend/settings/base.py`
- `/Users/embario/Documents/juke/backend/settings/urls.py`
- `/Users/embario/Documents/juke/docker-compose.yml`
- `/Users/embario/Documents/juke/backend/tests/*`
- Commands:
- `docker compose exec backend python manage.py test`
- `docker compose exec backend ruff check .`
- Risks:
- Hidden dependencies on removed legacy code in downstream services/tests.
- Insufficient observability before cutover.
- Partially deleting the recommender app while leaving orphaned models/tasks/routes behind would create operational dead weight and migration confusion.

## Handoff

- Completed:
- Next:
- Blockers:
