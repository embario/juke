---
id: mlcore-isrc-alias-enrichment
title: MLCore ISRC alias enrichment for canonical items
status: ready
priority: p1
owner: unassigned
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - identity
complexity: 3
updated_at: 2026-06-09
---

## Goal

Attach ISRC identities to MLCore canonical recording items through the existing canonical alias identity graph, making ISRC a reusable bridge from canonical MusicBrainz/ListenBrainz identities to downstream music-platform URIs.

## Scope

- Match `mlcore_canonical_item` rows with `item_type=recording_mbid` to the MusicBrainz ISRC bridge.
- Insert aliases into `mlcore_canonical_item_alias` with:
  - `source=isrc`
  - `resource_type=recording`
  - `source_id=<ISRC>`
- Preserve source version and match evidence.
- Report canonical coverage and unresolved holes.
- Treat ISRC aliases as graph edges that can support Spotify, Apple Music, YouTube Music, and other platform URI enrichment over time.

## Out Of Scope

- Raw MusicBrainz dump loading.
- Spotify API calls.
- Reassigning canonical identity conflicts without an explicit conflict policy.

## Acceptance Criteria

- ISRC identity rows use the same `mlcore_canonical_item_alias` graph as Spotify, MusicBrainz, and ListenBrainz aliases.
- ISRC bridge results are represented as identity-graph aliases, not as a parallel authoritative identity system.
- Alias materialization is idempotent.
- Conflicts are counted and surfaced, not silently overwritten.
- Coverage report includes:
  - total canonical items
  - `recording_mbid` items
  - `recording_mbid` items with at least one ISRC
  - `recording_msid` items still unresolved to MBID/ISRC
  - Spotify-track canonical items already covered
- Tests cover many-ISRC recordings, conflicts, and idempotency.

## Execution Notes

- This should combine into the existing identity graph rather than create a second authoritative graph.
- A separate MusicBrainz bridge table is allowed as an ingestion/cache artifact, but request-time identity should go through canonical aliases.
- Platform-specific URI resolvers should consume `source=isrc` graph aliases and write their resolved external IDs back into the same alias table with provider-specific `source` values.
- Risks:
  - `source=isrc` aliases may map one ISRC to multiple canonical items if MusicBrainz data conflicts; conflict handling needs a clear policy.

## Handoff

- Completed: task created.
- Next: implement alias materializer after bridge ingestion.
- Blockers: `mlcore-musicbrainz-isrc-bridge-ingestion`.
