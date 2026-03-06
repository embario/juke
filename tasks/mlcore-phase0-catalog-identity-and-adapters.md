---
id: mlcore-phase0-catalog-identity-adapters
title: ML Core Phase 0 - Catalog identity augmentation and adapter IDs
status: review
priority: p1
owner: codex
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - migrations
complexity: 4
updated_at: 2026-03-05
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
  - Upgraded backend to Python 3.14 (`backend/Dockerfile`, `backend/pyproject.toml`) for native `uuid.uuid7()`.
  - `juke_id` (UUIDv7, unique, non-null, auto-default) added to `MusicResource` abstract base → inherited by Genre/Artist/Album/Track. Removed redundant `db_index` (unique implies index; avoids PostgreSQL reverse-migration churn).
  - `mbid` (UUID, nullable, indexed) added to Artist/Album/Track only (Genre intentionally excluded per arch §5.1).
  - Migration `catalog/migrations/0003_*.py` uses 3-step pattern (AddField null=True → RunPython backfill → AlterField unique=True) per Django docs on unique callable-default fields. Reversibility verified.
  - Four adapter models added (`GenreExternalIdentifier`, `ArtistExternalIdentifier`, `AlbumExternalIdentifier`, `TrackExternalIdentifier`) with FK `to_field='juke_id'`, `unique_together=('source','external_id')`, explicit `db_table` names matching arch spec. Migration `catalog/migrations/0004_*.py`.
  - `IdentityResolver` service (`catalog/services/identity.py`) implementing precedence: `juke_id` → `mbid` → adapter. Deterministic no-fall-through on miss. `select_related` on adapter lookups.
  - Tests: `tests/unit/test_external_identifiers.py` (9 tests), `tests/unit/test_identity_resolver.py` (17 tests). Full suite: 214 tests pass.
- Next:
  - Phase 1 work (`mlcore-phase1-metadata-cooccurrence`) can now reference `juke_id` as the canonical join key.
  - Consider backfilling `ExternalIdentifier` rows from existing `spotify_id` values once adapter-write paths are exercised.
- Blockers:
  - None.
