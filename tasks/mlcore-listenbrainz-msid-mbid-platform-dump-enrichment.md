---
id: mlcore-listenbrainz-msid-mbid-platform-dump-enrichment
title: MLCore ListenBrainz dump enrichment for MSID, MBID, ISRC, and platform IDs
status: ready
priority: p1
owner: unassigned
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - data-ingestion
  - identity
complexity: 5
updated_at: 2026-06-11
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

- Completed: task created from identity graph hydration design.
- Next: implement manifest discovery and a small extractor prototype against one monthly dump.
- Blockers: none.
