---
id: mlcore-listenbrainz-msid-mbid-platform-dump-enrichment
title: MLCore ListenBrainz dump enrichment for MSID, MBID, ISRC, and platform IDs
status: in_progress
priority: p1
owner: codex
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - data-ingestion
  - identity
complexity: 5
updated_at: 2026-06-17
---

## Goal

Mine ListenBrainz dumps for identity evidence that enriches MLCore's local identity graph, especially MSID->MBID mappings and any available ISRC, Spotify, or other platform identifiers.

## Scope

- Discover latest ListenBrainz full and incremental dump manifests and sizes.
- Download raw dump artifacts to cold storage.
- Parse listens and metadata fields for:
  - `recording_msid`
  - `recording_mbid`
  - `isrc`
  - `spotify_id`
  - `origin_url`
  - `music_service`
  - other platform URLs/IDs when present
- Build compact extracted identity fact tables in cold or warm storage.
- Materialize high-confidence facts into MLCore identity graph aliases or canonical redirects.
- Support incremental refreshes after an initial full dump.

## Out Of Scope

- Paid vendor API enrichment.
- Spotify API hydration from ISRC; see `mlcore-platform-uri-hydration-from-isrc`.
- Training model changes.

## Acceptance Criteria

- Dump discovery reports source version, files, compressed size, and required local free space before download.
- Extractor produces counts for MSID, MBID, ISRC, Spotify, and other platform IDs.
- MSID->MBID mappings are confidence scored and conflict aware.
- Spotify URLs/IDs and other platform URLs are normalized into provider-specific alias candidates.
- Raw dumps and broad staging remain in cold storage.
- Active aliases and canonical redirects land in hot storage with explicit tablespace placement.
- Job exposes progress, throughput, ETA, error, and coverage metrics.
- Tests cover metadata extraction, provider URL normalization, MSID->MBID conflict handling, idempotency, and incremental replay.

## Execution Notes

- ListenBrainz docs state full dumps and incremental dumps are available, with listens split into monthly JSON-lines files.
- Deleted listens require periodic full re-imports for full accuracy.
- Treat user/client-submitted provider metadata as evidence, not automatic truth.
- Prefer exact MSID+MBID facts over fuzzy metadata matching.

## Resource Notes

- Initial storage must be discovered from the live dump manifest; do not hard-code a stale dump size.
- Expect this to be the largest cold-storage consumer in the identity enrichment plan.
- Hot-storage growth is driven by extracted unique identity facts, not raw listens.

## Handoff

- Completed: confirmed exact MSID-to-MBID evidence is embedded in the locally materialized ListenBrainz shards.
- Completed: added resumable per-shard extraction, cold evidence/checkpoint tables, exact conflict classification, 64-bit ingestion counters, progress/throughput/ETA reporting, and safe hot canonical redirects.
- Completed: real-data validation scanned 8 shards and materialized 6 exact redirects with no conflicts.
- Completed: full 261-shard production backfill succeeded; run ID `699b2eb7-4d4b-48f2-a713-dff7765f342c`.
- Completed: scanned 1,751,330,064 listens, found 252,222,425 mapped observations, stored 24,133,470 global unique MSID-to-MBID rows, classified 15,481,819 clean active mappings, and excluded 4,085,990 conflicting MSIDs.
- Completed: identity graph expansion inserted all 7,691,107 missing MSID canonical rows for clean mappings whose MBID target already existed.
- Completed: clean MSID-to-MBID coverage reached 15,481,819 active canonical redirects.
- Completed: strict conflict resolver `shard-dominance-v1` promoted 40,198 additional conflict MSIDs using `winner_share >= 0.95` and `winner_shard_observation_count >= 2`; 0 redirect conflicts.
- Current totals: 15,522,017 active redirects from ListenBrainz identity work; conflict-resolution evidence table is 20 MB cold storage.
- Completed: added `ingest_incremental_identity`, an incremental ListenBrainz identity ingestion engine that syncs new deltas, materializes shards, imports bridge evidence, expands clean canonical MSIDs, and applies strict conflict resolution.
- Completed: added `scripts/mlcore_identity_metrics.sh` and a Grafana canonical identity inventory panel for MSIDs, MBIDs, ISRC evidence, vendor aliases, redirects, and bridge/conflict counts.
- Next: expose the completed-run metrics on the identity observability dashboard task and design a second-pass ambiguity analysis for conflicts below the strict dominance threshold.
- Blockers: none.
