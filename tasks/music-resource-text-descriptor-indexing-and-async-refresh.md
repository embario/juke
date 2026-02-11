---
id: music-resource-text-descriptor-indexing
title: Define best route for text descriptor indexing across music resources with async refresh
status: ready
priority: p1
owner: unassigned
area: platform
label: BACKEND/ML
complexity: 4
updated_at: 2026-02-11
---

## Goal

Define and approve the best technical approach to index all text descriptors for linked music resources (genres, artists, albums, tracks) so the index can be built now and refreshed asynchronously later without blocking user-facing flows.

## Scope

- Audit existing descriptor sources in the current data model and enrichment flows.
- Propose and select the canonical indexing architecture (storage model, document shape, keys, and lookup strategy).
- Define asynchronous refresh strategy (full backfill + incremental refresh + retry/repair behavior).
- Specify orchestration approach (Celery tasks/queues, batching, idempotency, and failure handling).
- Define observability and operations needs (metrics, logs, run status, dead-letter/retry posture).
- Provide rollout plan with migration and backfill sequencing.

## Out Of Scope

- Full implementation of the indexing pipeline.
- UI/UX work for search or recommendation consumers.
- Model-quality tuning for ranking/recommendation logic.

## Acceptance Criteria

- A written recommendation identifies one primary indexing approach and at least one rejected alternative with tradeoffs.
- Canonical descriptor schema is defined for all resource types (genre, artist, album, track), including field provenance and normalization rules.
- Async refresh contract is defined for:
  - initial backfill
  - scheduled refresh
  - targeted resource reindex
  - idempotent rerun after failure
- Task orchestration design includes queue routing, chunk sizing, retries, and checkpoint/resume behavior.
- Rollout plan includes migration order, backfill strategy, and zero/low-downtime considerations.
- Test plan is documented (unit, integration, operational smoke checks).

## Execution Notes

- Key files:
  - `backend/catalog/models.py`
  - `backend/catalog/services/detail_enrichment.py`
  - `backend/catalog/services/catalog_crawl.py`
  - `backend/catalog/tasks.py`
  - `settings/base.py`
- Commands:
  - `docker compose exec backend python manage.py test`
  - `docker compose exec backend ruff check .`
- Risks:
  - Descriptor quality drift across sources (`spotify_data`, enrichment payloads, `custom_data`).
  - Long-running backfills causing queue contention with existing workloads.
  - Missing idempotency leading to duplicate index writes or stale state.
  - Incomplete observability making partial failures hard to recover.

## Handoff

- Completed:
- Next:
  - Produce architecture recommendation doc and implementation plan.
  - Align on storage/index target and refresh cadence.
  - Split follow-on implementation work into execution tasks.
- Blockers:
