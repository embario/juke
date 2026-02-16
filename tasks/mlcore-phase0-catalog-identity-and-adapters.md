---
id: mlcore-phase0-catalog-identity-adapters
title: ML Core Phase 0 - Catalog identity augmentation and adapter IDs
status: ready
priority: p1
owner: unassigned
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - migrations
complexity: 4
updated_at: 2026-02-16
---

## Goal

Augment existing catalog models to become the canonical identity layer for the independent ML core using `juke_id` (UUIDv7), `mbid`, and per-resource external ID adapter tables.

## Scope

- Add `juke_id` UUIDv7 fields to `Artist`, `Album`, `Track`, `Genre`.
- Add nullable indexed `mbid` fields to `Artist`, `Album`, `Track`.
- Create per-resource adapter tables:
- `catalog_artist_external_id`
- `catalog_album_external_id`
- `catalog_track_external_id`
- `catalog_genre_external_id`
- Add data migration/backfill for existing rows.
- Add resolver utilities for canonical ID precedence (`juke_id` -> `mbid` -> adapter IDs).

## Out Of Scope

- Recommendation scoring implementation.
- Embedding extraction/training jobs.

## Acceptance Criteria

- Catalog entities have stable non-null `juke_id` values (UUIDv7).
- Adapter tables enforce uniqueness on (`source`, `external_id`).
- Resolver returns deterministic canonical resource IDs for known mappings.
- Migration is reversible and passes backend test suite.

## Execution Notes

- Idea rank: `#9`
- Portfolio classification: `experimental`
- Program linkage: this task is one phase in the broader MLCore roadmap (`mlcore-phase0` to `mlcore-phase4` + dataset viability).
- Key files:
- `/Users/embario/Documents/juke/backend/catalog/models.py`
- `/Users/embario/Documents/juke/backend/catalog/migrations/*`
- `/Users/embario/Documents/juke/backend/catalog/services/*` (new identity resolver)
- Commands:
- `docker compose exec backend python manage.py makemigrations catalog`
- `docker compose exec backend python manage.py migrate`
- `docker compose exec backend python manage.py test`
- Risks:
- UUIDv7 generation compatibility in Python/Django dependencies.
- Backfill runtime if catalog row counts are large.

## Handoff

- Completed:
- Next:
- Blockers:
