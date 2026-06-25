---
id: mlcore-platform-uri-hydration-from-isrc
title: MLCore platform URI hydration from ISRC inventory
status: review
priority: p1
owner: codex
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - identity
  - design
complexity: 3
updated_at: 2026-06-22
---

## Goal

Design and implement a background hydration job that starts from MLCore's known ISRC aliases and enriches the shared identity graph with Spotify track IDs/URIs and, later, other platform URIs.

## Context

MLCore needs a durable identity graph so downstream clients can send and receive provider-native identifiers without each request doing expensive external identity resolution.

The forward path is:

```text
canonical item -> MBID/MSID -> ISRC -> provider URI
```

This task attacks the second half directly:

```text
known ISRC inventory -> provider search/lookup -> platform aliases
```

Spotify is the first provider because the downstream recommendation contract currently expects Spotify track IDs/URIs.

## Scope

- Build a provider-generic hydration design with Spotify as the first concrete provider.
- Select ISRC aliases from `mlcore_canonical_item_alias` where `source=isrc`.
- Prioritize hydration by serving value:
  - recently recommended candidates
  - high-degree/high-score cooccurrence outputs
  - popular ListenBrainz corpus items
  - recent unresolved recommendation attempts
- Query Spotify Search using `isrc:<code>` and `type=track`.
- Store successful provider matches back into `mlcore_canonical_item_alias`.
- Store evidence/metadata sufficient to audit the match:
  - ISRC used
  - provider track ID
  - provider URI
  - match confidence
  - market used
  - title/artist/duration comparison if available
  - raw provider result hash or compact evidence payload
- Record no-match and ambiguous-match outcomes so failed ISRCs are not retried aggressively.
- Expose progress, throughput, match rate, ambiguity rate, rate-limit count, and backlog metrics.

## Out Of Scope

- Training ML models on provider metadata.
- Full-corpus eager hydration without a rate-limit and quota plan.
- Replacing MusicBrainz dump ingestion.
- Building every provider integration in the first pass.

## Acceptance Criteria

- Design doc or ADR describes hydration queue, provider interface, retry policy, storage shape, and serving impact.
- Spotify hydration command/task can process a bounded batch of ISRC aliases.
- Hydration is idempotent by provider/source ID and canonical item.
- Ambiguous results are held for review or lower-confidence storage; they do not silently become active aliases.
- Rate limiting honors Spotify `429` responses and `Retry-After` when present.
- Metrics show:
  - pending ISRC aliases
  - processed ISRC aliases
  - provider matches created
  - no-match outcomes
  - ambiguous outcomes
  - retries/backoff/rate-limited calls
  - estimated backlog completion time at current throughput
- Tests cover exact match, no match, ambiguous match, existing alias, provider error, and rate-limit retry.

## Design Notes

### Alias Representation

Use the existing identity graph as durable truth:

```text
source=spotify
resource_type=track
source_id=<spotify_track_id>
metadata.spotify_uri=spotify:track:<spotify_track_id>
metadata.match_source=isrc
metadata.match_isrc=<isrc>
```

Avoid creating a second platform-mapping graph unless there is a concrete read/write performance need. A separate hydration attempt table is acceptable for queueing, retry state, and audit history.

### Hydration Queue

Prefer a resumable queue/table over ad hoc scans once the first batch prototype works:

```text
canonical_item_id
isrc
provider
priority
status
attempt_count
next_attempt_at
last_error
match_result
source_version
created_at
updated_at
```

The queue can be generated from active ISRC aliases and refreshed periodically.

### Provider Interface

Keep Spotify-specific behavior behind an interface:

```text
hydrate(provider="spotify", identifier_type="isrc", identifier=<isrc>)
  -> zero, one, or many provider candidates
```

That keeps future Apple Music/YouTube Music/etc. integrations from changing canonical identity semantics.

## Tradeoffs

- Eager full-corpus hydration creates the richest graph, but it is likely slow, rate-limit-heavy, and may resolve many items that never get served.
- Lazy request-time hydration reduces upfront work, but makes recommendations slower and less reliable during user requests.
- Prioritized background hydration is the best first production shape: it keeps request-time serving fast while focusing API calls on items likely to matter.
- Storing only active aliases keeps serving simple, but loses useful evidence about ambiguous/no-match cases. A hydration-attempt table preserves auditability without polluting the active graph.
- ISRC search is strong, but not perfect. Multiple Spotify tracks can share an ISRC across territories, explicit/clean variants, remasters, or relinked tracks. Confidence scoring and ambiguity handling are required.

## Source Notes

- Spotify Search supports `isrc` filters for track search.
- Spotify track objects include track IDs, URIs, external URLs, and external IDs such as ISRC.
- Spotify rate limits are based on calls in a rolling 30-second window and may return `429`; exact public limits vary by quota mode.
- Design reference: `docs/arch/MLCORE_IDENTITY_GRAPH_HYDRATION_DESIGN.md`.

## Handoff

- Implemented durable cold-storage hydration queue/run models, exact-ISRC Spotify
  provider adapter, singleton PostgreSQL worker lease, expiring item leases, bounded
  retry/backoff, adaptive `429` handling, textfile metrics, and management command.
- Added dedicated hydration credential settings; shared social-auth credentials are a
  development fallback.
- Production migration `0033` applied on Neptune.
- Pilot run `8ce3f580-6e29-4c98-99de-f8335654675f` completed 300 requests in 299.5s:
  170 matched, 124 no-match, 6 ambiguous, 0 retries, and 0 rate limits.
- Exact starting backlog: 1,857,666 ISRCs. Measured-rate ETA is 21.46 days, or 23.6
  days with a 10% operational contingency.
- Full queue seed and 1 request/s background hydration launched on 2026-06-22.
- Full queue contains 1,857,660 cold rows and occupies 613,629,952 bytes including
  indexes immediately after seeding. Production run:
  `85865fd9-2c33-43c6-9c54-6d5fcf0d65a9`.
- Next: monitor rate limits and observed ETA; configure a dedicated Spotify app before
  increasing the rate ceiling; add explicit reconciliation policy for ambiguous rows.
- Blockers: none for the conservative 1 request/s run.
