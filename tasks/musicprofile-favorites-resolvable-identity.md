---
id: musicprofile-favorites-resolvable-identity
title: MusicProfile favorite_* fields store name strings — make them resolvable to juke_ids
status: blocked
priority: p2
owner: unassigned
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - data-quality
complexity: 3
updated_at: 2026-03-06
---

## Goal

`MusicProfile.favorite_tracks` / `favorite_artists` / `favorite_albums` currently hold bare
display-name strings. Make them resolvable to canonical catalog identity (`juke_id`) so ML
pipelines can consume explicit user-preference signal.

## Problem

Discovered during ML Core Phase 1 eval harness work (2026-03-06):

| Evidence | File:Line | What it shows |
|---|---|---|
| Model def | `backend/juke_auth/models.py:21-24` | `JSONField(default=list)` — untyped, no schema |
| Serializer | `backend/juke_auth/serializers.py:30-33` | Plain `fields` entry, client payload stored verbatim |
| Consumer | `backend/recommender/services/taste.py:9,16` | `_normalized_list()` calls `.strip()` on every element — string-list contract is enforced at read time |
| Test fixture | `backend/tests/unit/test_recommender_taste.py:32-35` | `favorite_tracks=['Lateralus', 'lateralus']` |
| Seed cmd | `backend/juke_auth/management/commands/seed_world_data.py:141-142` | Populates name-string lists only |
| Dev fixture | `backend/juke_auth/fixtures/dev.json:68` | `"favorite_genres": ["rock", "jazz"]` |

Why resolution fails: `Track.name` (`catalog/models.py:109`) is `CharField(max_length=1024)`,
**not unique**. "Intro" / "Interlude" / "Outro" collide across thousands of albums. No
artist/album context is stored alongside the name, so `Track.objects.filter(name=...)` is
non-deterministic.

Contrast: `SearchHistoryResource.resource_id` is an integer PK — one-shot exact resolution
via `Track.objects.filter(pk__in=pks).values_list('pk', 'juke_id')`, which is what the Phase 1
co-occurrence trainer already does (`mlcore/services/cooccurrence.py:77-79`).

## Scope

- Decide storage shape: either list-of-objects (`[{"name": "...", "juke_id": "..."}]`) in the
  existing JSONField, or a proper M2M/through table keyed on `juke_id`. Align with whatever
  `onboarding-contract-profile-unification` picks as the canonical contract.
- Update `MusicProfileSerializer` to validate + resolve incoming favorites against the catalog
  at write time (accept either `juke_id` directly or `{name, spotify_id}` tuples that resolve
  via the identity adapter tables from Phase 0).
- Data migration: best-effort resolution of existing string values. Unresolvable names stay as
  `{"name": "...", "juke_id": null}` — do not silently drop user preferences.
- Update `recommender/services/taste.py:profile_to_payload()` to emit juke_ids.
- Update web/iOS/Android onboarding forms to send the new payload shape.

## Out Of Scope

- Favorite genres: `Genre.name` is effectively unique in practice and already resolvable;
  leave the existing string-list shape unless the contract task decides otherwise.
- Retroactive catalog crawl to improve resolution hit-rate on legacy data.

## Acceptance Criteria

- A `favorite_tracks` entry can be joined to `catalog_track.juke_id` without name matching.
- Existing profiles with legacy string-list data load without error and preserve the
  display name even when `juke_id` is null.
- `mlcore/services/evaluation.py` can build LOO trials from `MusicProfile.favorite_tracks`
  in addition to `SearchHistoryResource` baskets (see Handoff below).
- Contract tests cover the new payload shape on all four clients.

## Execution Notes

- Key files:
  - `backend/juke_auth/models.py`
  - `backend/juke_auth/serializers.py`
  - `backend/juke_auth/migrations/` (new data migration)
  - `backend/recommender/services/taste.py`
  - `backend/mlcore/services/evaluation.py` (integration point — see Handoff)
  - `web/src/features/auth/components/onboarding/**`
  - `mobile/ios/juke/juke-iOS/Onboarding/**`
  - `mobile/android/juke/app/src/main/java/fm/juke/mobile/ui/onboarding/**`
- Commands:
  - `docker compose exec backend python manage.py makemigrations juke_auth`
  - `docker compose exec backend python manage.py test`
- Risks:
  - Best-effort name resolution during data migration will have a low hit-rate if the catalog
    is sparse at migration time. Run the migration after a catalog crawl, not before.
  - Four clients must cut over in lockstep or the serializer needs to accept both shapes
    during a transition window.

## Handoff

- Completed:
  - Root cause traced and documented (above).
- Next:
  - Wait for `onboarding-contract-profile-unification` to settle the canonical payload shape,
    then implement against it.
  - **ML eval follow-up (required):** Phase 1's `mlcore/services/evaluation.py` currently
    builds leave-one-out trials from `SearchHistoryResource` baskets only — a deliberate
    scope cut because favorites aren't resolvable today. Once this task lands, extend
    `build_loo_dataset()` (or equivalent) to also emit trials from `MusicProfile.favorite_tracks`.
    Favorites are a stronger explicit-preference signal than search-session co-clicks;
    mixing both sources will give the promotion gates a more representative eval set.
- Blockers:
  - `onboarding-contract-profile-unification` — shares the same serializer + client surfaces;
    migrating twice would be wasteful.
