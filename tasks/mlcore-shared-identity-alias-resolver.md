---
id: mlcore-shared-identity-alias-resolver
title: MLCore shared identity alias resolver for A/B isolation
status: review
priority: p1
owner: codex
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - recommender
  - identity
complexity: 4
updated_at: 2026-06-08
---

## Goal

Implement the minimum production-shaped identity boundary needed for A/B agent evaluation where `model_a` and `model_b` run isolated Django/Postgres/Redis/web stacks, while both call one shared read-only MLCore recommender service.

The shared MLCore service must resolve stable external music IDs, such as Spotify track IDs and MusicBrainz recording MBIDs, into MLCore canonical item IDs without relying on model-local catalog IDs.

## Sequencing Question

Before implementation starts, decide task order:

- Option A: Do this MLCore isolation and alias resolver work first, so the serving identity contract is safe before more cooccurrence validation.
- Option B: Finish the current cooccurrence training validation first, then wire the isolation-safe identity boundary around the trained recommender.

Decision guidance:

- Prefer this task first if A/B evaluation or multi-stack serving is the next operational milestone.
- Prefer cooccurrence training first if the immediate milestone is validating the current Neptune cooccurrence table and promotion metrics before changing serving contracts.
- Record the decision in this task's handoff notes before coding begins.

## Context

Juke is normally a monolithic Django backend where catalog, MLCore, and recommender tables are co-resident. In that mode, identity resolution is mostly handled by local joins, for example `mlcore_canonical_item.track_id -> catalog_track.juke_id`.

For A/B evaluation:

- `model_a` and `model_b` each have their own writable backend database.
- Their local `catalog_track.juke_id` values must not be used as shared recommender identities.
- The shared MLCore/recommender plane owns the heavy corpus and must remain read-only for A/B clients.
- Backends should call MLCore using stable external identifiers such as Spotify track IDs and MusicBrainz recording MBIDs.
- MLCore should resolve those identifiers to its own `mlcore_canonical_item.id`.

Existing MLCore identity behavior:

- `mlcore_canonical_item` already exists.
- It has `id`, `item_type`, `canonical_key`, optional `track` FK to `catalog.Track.juke_id`.
- `backend/mlcore/services/canonical_items.py` defines deterministic canonical IDs using `uuid.uuid5(CANONICAL_ITEM_NAMESPACE, f"{item_type}:{key_value}")`.
- Current item types include `recording_mbid`, `spotify_track`, `recording_msid`, and `catalog_track`.
- Current helper behavior prefers MBID, then Spotify ID, then catalog track `juke_id`.

Problem:

If a canonical item was created as `recording_mbid:<mbid>`, a backend request containing only `spotify_track:<spotify_id>` may fail to resolve unless MLCore has an alias mapping. We need an explicit alias layer: many external aliases -> one MLCore canonical item.

## Scope

- Add an MLCore-owned alias model/table, tentatively `mlcore_canonical_item_alias`.
- Implement alias materialization from the shared corpus catalog tables.
- Add a read-only resolver endpoint to the recommender engine, such as `POST /resolve`.
- Add backend recommender client support for the resolver.
- Preserve the existing name-based `/api/v1/recommendations/` behavior.
- Add focused tests for the alias model, alias population, resolver endpoint, and backend client payload.
- Document the A/B identity contract in this task handoff or a short docs note.

## Suggested Alias Schema

`mlcore_canonical_item_alias`:

- `id`: UUID primary key
- `canonical_item`: FK to `mlcore.CanonicalItem`, cascade delete
- `source`: string or choices; initially support at least `spotify`, `musicbrainz`, `listenbrainz`, `juke_catalog`
- `resource_type`: string or choices; initially support at least `track`, but keep generic enough for future artist/album support
- `source_id`: string
- `confidence`: float or decimal, default `1.0`
- `source_version`: string, blank allowed
- `status`: string or choices, default `active`; consider `active`, `retired`, `conflict`
- timestamps
- unique constraint on `(source, resource_type, source_id)`
- index on `canonical_item`
- lookup index for `(source, resource_type, source_id)`

The key read path must be fast:

```sql
SELECT canonical_item_id
FROM mlcore_canonical_item_alias
WHERE source = ? AND resource_type = ? AND source_id = ?
```

## Alias Population

Implement a service that can materialize aliases from the shared corpus catalog tables:

- For each `catalog.Track` with `spotify_id`, create alias:
  - `source=spotify`
  - `resource_type=track`
  - `source_id=<track.spotify_id>`
- For each `catalog.Track` with `mbid`, create alias:
  - `source=musicbrainz`
  - `resource_type=recording`
  - `source_id=<track.mbid>`
- For each `catalog.TrackExternalIdentifier`, create alias:
  - `source=<external.source>`
  - `resource_type=track`
  - `source_id=<external.external_id>`
- Each alias should point to the same `CanonicalItem` selected by the existing canonical identity priority in `identity_from_track(track)`.
- If a track has an MBID, the Spotify alias should point to the `recording_mbid:<mbid>` canonical item, not create a separate Spotify canonical item.
- Reuse or extend `bulk_ensure_canonical_items_for_tracks` where appropriate.
- Make alias population idempotent.
- Handle conflicts deterministically. Do not silently reassign an existing alias to a different canonical item unless the conflict policy is explicit. For the first implementation, leave existing mappings untouched and record/report conflicts.

## Resolver Endpoint

Add a read-only endpoint to `backend/recommender_engine/app/main.py`, for example:

`POST /resolve`

Request shape:

```json
{
  "items": [
    {
      "source": "spotify",
      "resource_type": "track",
      "source_id": "3n3Ppam7vgaVa1iaRUc9Lp"
    }
  ]
}
```

Response shape:

```json
{
  "items": [
    {
      "source": "spotify",
      "resource_type": "track",
      "source_id": "3n3Ppam7vgaVa1iaRUc9Lp",
      "canonical_item_id": "<uuid or null>",
      "status": "resolved|unresolved|conflict|invalid",
      "canonical_key": "recording_mbid:<mbid>",
      "item_type": "recording_mbid"
    }
  ],
  "model_version": "...",
  "generated_at": "..."
}
```

Endpoint constraints:

- Must be read-only.
- Should only query alias/canonical/catalog metadata.
- Must not create aliases at request time.
- Should tolerate batch requests.
- Should normalize whitespace and reject empty IDs.
- Should include enough metadata for debugging.
- Must not expose internal local `model_a`/`model_b` IDs as the primary identity.

## Recommendation Contract Direction

Near term:

- Keep existing name-based recommendation endpoint working.
- Add identity resolution plumbing and tests.
- Optionally add identity-aware request fields such as `seed_items: [{source, resource_type, source_id, weight}]`.

Future-facing:

- Backend should resolve local app rows to external IDs, then call MLCore.
- MLCore should resolve external IDs to canonical item IDs.
- MLCore should rank using canonical item IDs.
- MLCore should return stable external identities and display metadata suitable for clients.
- The identity graph should accumulate bridge aliases such as ISRC plus platform URI aliases such as Spotify, Apple Music, YouTube Music, Deezer, or Tidal IDs as enrichment jobs prove them.
- Provider-specific URIs should remain aliases attached to canonical items; they should not become separate competing canonical identifiers unless no better canonical identity exists.

## Out Of Scope

- Do not use model-local `catalog_track.juke_id` from `model_a` or `model_b` as a cross-service identity.
- Do not require `model_a` or `model_b` to copy the heavy MLCore identity tables.
- Do not make the shared recommender DB writable from `model_a` or `model_b`.
- Do not build a full universal music identity platform.
- Do not replace the existing name-based recommendation API in this task.

## Acceptance Criteria

- Migration and model exist for canonical item aliases.
- Alias uniqueness and FK behavior are covered by tests.
- Alias materialization creates Spotify and MusicBrainz aliases for tracks.
- A Spotify alias points to the MBID-preferred canonical item when MBID exists.
- Alias materialization is idempotent.
- Alias conflicts are reported without silently reassigning active mappings.
- `POST /resolve` returns resolved, unresolved, conflict, and invalid cases as designed.
- Backend recommender client can post the expected `/resolve` payload.
- Existing `/api/v1/recommendations/` tests continue to pass.
- A short handoff note explains the A/B identity contract and the chosen sequencing relative to cooccurrence training.

## Execution Notes

- Key files:
  - `backend/mlcore/models.py`
  - `backend/mlcore/services/canonical_items.py`
  - `backend/recommender_engine/app/main.py`
  - `backend/recommender/services/client.py`
  - `backend/recommender/views.py`
  - `backend/recommender/serializers.py`
  - relevant tests under `backend/tests/`
- Suggested commands:
  - `docker compose exec backend python manage.py makemigrations mlcore`
  - `docker compose exec backend python manage.py test tests.unit.test_cooccurrence_trainer tests.unit.test_engine_scorers`
  - `docker compose exec backend python manage.py test tests.api.test_recommendations`
- Operational notes:
  - This is meant to run on Neptune, where the heavy MLCore corpus lives.
  - The shared recommender service should use a read-only database role for serving `/resolve` and `/recommend`.
  - Alias materialization is an admin/offline operation run during corpus prep, not during A/B request handling.
  - Keep migrations compatible with existing data.
- Risks:
  - Conflicting external IDs can point at different canonical items if corpus metadata is inconsistent.
  - The cooccurrence recommender currently ranks over MLCore canonical item IDs, while clients may think in provider IDs or local catalog IDs.
  - Doing this before the clean cooccurrence run may delay model validation; doing it after may require reworking serving assumptions.

## Handoff

- Completed:
  - Sequencing recommendation recorded on 2026-05-30: finish the cooccurrence training validation first, then implement this MLCore shared identity alias resolver.
  - Rationale: the cooccurrence path already has a large Neptune training artifact, paused incremental sync, and explicit operational handoff steps. Validating or replacing that run first answers whether the current ranker is worth serving at all. The alias resolver is the right serving boundary for A/B isolation, but it wraps the recommender; it should follow once the recommender table/evaluation state is known-good.
  - Sequencing override recorded on 2026-05-30: user explicitly resumed this isolation task, so implementation started before the cooccurrence validation handoff is fully closed.
  - Added first implementation slice:
    - `mlcore_canonical_item_alias` model/migration with alias uniqueness, canonical-item FK, lookup indexes, status, confidence, source version, and metadata.
    - Alias materialization service and `materialize_canonical_aliases` management command. Materialization is offline/admin-only: it creates Spotify track, MusicBrainz recording, and `TrackExternalIdentifier` aliases against the existing MBID-first `CanonicalItem` identity, remains idempotent, and reports conflicts without reassigning existing aliases.
    - Read-only recommender-engine `POST /resolve` endpoint that accepts external IDs, normalizes whitespace/case, and returns `resolved`, `unresolved`, `conflict`, or `invalid` per item.
    - Backend recommender client `resolve_items()` helper for model-local stacks to call shared MLCore without using local catalog UUIDs.
  - A/B identity contract for this slice: model-local backends should send stable external identifiers such as `spotify:track:<id>` or `musicbrainz:recording:<mbid>` to shared MLCore. Shared MLCore resolves those aliases to its own `mlcore_canonical_item.id`, ranks only in canonical-item space, and must not depend on `model_a`/`model_b` local `catalog_track.juke_id` values.
  - 2026-05-31 follow-up hardening:
    - Verified the alias model/migration, materialization service, backend client helper, and resolver response behavior with focused Django tests.
    - Verified the recommender-engine resolver imports and response shaping inside the `recommender-engine` container by calling the FastAPI handler directly; the container does not include `httpx`, so `fastapi.testclient.TestClient` is not available there.
    - Tightened `/resolve` SQL to join against the exact requested alias tuples instead of independent `ANY()` filters, avoiding broad cross-product matching for mixed-source batches.
  - 2026-06-08 isolation-boundary serving slice:
    - Added identity-aware MLCore engine endpoints:
      - `POST /engine/recommend/cooccurrence/identity`
      - `POST /engine/recommend/metadata/identity`
    - Added authenticated backend proxy endpoint `POST /api/v1/recommendations/mlcore/` so model-local backend stacks can call the shared MLCore service with external IDs instead of local catalog IDs.
    - Added backend recommender client helper `fetch_identity_recommendations(ranker, payload)`.
    - Identifier contract for this slice: model-local stacks should prefer Spotify track IDs (`source=spotify`, `resource_type=track`) for seeds/exclusions when available; MusicBrainz recording MBIDs (`source=musicbrainz`, `resource_type=recording`) remain accepted fallback identifiers. Local Juke catalog UUIDs are intentionally not accepted by the backend proxy.
    - Resolution behavior: MLCore resolves seed/exclusion items via `mlcore_canonical_item_alias`; unresolved, conflict, and invalid seeds are reported in `unresolved_seed_items`; ranking runs only for resolved canonical item IDs. Recommendation results use `canonical_item_id` rather than local catalog IDs. If no seed resolves, the response is empty with `resolved_seed_count=0` rather than falling back to local IDs.
    - Failure behavior: backend proxy returns `503 {"detail": "recommendations unavailable"}` when the shared MLCore engine cannot be reached.
    - Added focused tests for the engine identity-ranking flow, backend client payloads, and authenticated backend proxy behavior.
  - 2026-06-08 canonical alias operational hardening:
    - Changed `materialize_canonical_aliases` / `materialize_track_aliases()` to process catalog tracks in bounded batches, defaulting to 10,000 tracks per batch, so Neptune-scale alias materialization does not load the full catalog into Python memory or issue one corpus-wide alias lookup.
    - Added `--batch-size` to the management command for operational tuning.
    - Marked `mlcore_canonical_item` and `mlcore_canonical_item_alias` as hot-path tables and added migration `0026_canonical_identity_hot_tablespace` to move both tables and their indexes to `juke_mlcore_hot` on PostgreSQL.
    - Added focused tests for alias table hot-storage metadata, batched materialization, invalid batch sizes, and cross-batch conflict reporting.
    - Added Prometheus textfile progress metrics for alias materialization:
      `mlcore_canonical_alias_materialization_*`. The default output path is
      `/srv/monitoring/node-exporter/textfile/mlcore_canonical_alias_materialization.prom`.
    - Updated `MLCore Full Ingestion` Grafana dashboard panels to show alias
      materialization active state, progress, ETA, throughput, and counters.
    - Corrected alias materialization to cover MLCore-native canonical items,
      not only local `catalog_track` rows. The command now defaults to a
      set-based Postgres path over `mlcore_canonical_item`, materializing:
      `recording_mbid` -> `musicbrainz:recording`, `recording_msid` ->
      `listenbrainz:recording`, and `spotify_track` -> `spotify:track`.
    - Kicked off the Neptune-scale self-alias job on 2026-06-08:
      `source_version=canonical-self-alias-2026-06-08`, `batch_size=100000`,
      backend container PID `1147`. Initial progress after seven batches:
      700,000 / 123,355,717 items processed, 700,000 aliases created,
      0 conflicts, ETA roughly 1h 44m at ~19.7k items/sec.
  - 2026-06-13 pre-PR resilience pass:
    - Enforced the supported external identity contract in both Django and the
      standalone MLCore service. Local Juke IDs and invalid provider/resource
      combinations are rejected at the boundary.
    - Added provider-aware normalization for Spotify IDs/URIs/URLs and canonical
      UUID normalization for MusicBrainz MBIDs and ListenBrainz MSIDs.
    - Bounded and deduplicated seed/exclusion inputs at 100 items each.
    - Added explicit `unresolved_exclude_items` reporting so exclusions are not
      silently treated as honored when resolution fails.
    - Added correlation request IDs and structured API/model/training/identity
      graph version provenance to identity-aware responses.
    - Added `502` handling for malformed MLCore responses while preserving `503`
      behavior for unavailable MLCore calls.
    - Unified Python and PostgreSQL alias IDs on the same deterministic MD5-based
      opaque UUID algorithm. Existing alias IDs remain valid and require no
      123M-row rewrite.
    - Added persistent `mlcore_canonical_alias_materialization_run` records with
      cumulative counters, source/algorithm versions, transactional per-batch
      checkpoints, failure state, and `--resume-run-id` support.
    - Added advisory-lock serialization and actual `INSERT ... RETURNING` counts
      so concurrent materializers preserve uniqueness and report real inserts.
    - Added tests for normalization, request bounds/deduplication, unresolved
      exclusions, invalid upstream responses, version provenance, concurrent
      inserts, clean migrations, and interruption/resume behavior.
    - Backfilled the completed 2026-06-08 canonical self-alias materialization
      as run `e74b17b6-470c-4753-84a7-2e2a72a11ef0` using the persisted
      Prometheus completion metrics: 123,355,717 items processed,
      123,355,716 aliases created, one existing alias, zero conflicts, and
      algorithm version `canonical-alias-v1-md5`. Identity-aware serving now
      reports this run and source version instead of `unversioned` provenance.
- Next:
  - Treat this isolation boundary as the prerequisite for MusicBrainz/ListenBrainz hydration work. Hydration should enrich the shared MLCore graph after this contract is merged, not before it.
  - Commit, push, and open the isolation-boundary PR from `codex/mlcore-isolation-boundary-service`.
  - Keep the interim response contract canonical-only: MLCore returns `canonical_item_id` recommendations, and model-local backend clients remain responsible for any vendor-specific output resolution they can perform locally until provider alias hydration is mature.
  - Complete the clean/current ListenBrainz-only cooccurrence training and evaluation handoff in `tasks/mlcore-phase1-metadata-and-cooccurrence-rankers.md`.
  - Add service API keys once the private-tailnet unauthenticated route has been exercised (`tasks/mlcore-service-api-keys.md`).
  - Consider enriching identity-aware recommendation responses with preferred external IDs/display metadata for downstream frontend clients.
- Blockers:
