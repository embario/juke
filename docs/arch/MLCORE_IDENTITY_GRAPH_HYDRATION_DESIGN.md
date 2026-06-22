# MLCore Identity Graph Hydration Design

Updated: 2026-06-22

## Goal

Build a durable, locally resolvable MLCore identity graph on Neptune that compounds over time. Downstream Juke apps should be able to send provider-native identifiers, such as Spotify track IDs, and receive provider-native recommendation outputs without request-time dependence on external resolution services whenever MLCore has already learned the mapping.

This is intentionally a long-running enrichment system. It does not need to finish overnight, or even within one or two years, as long as it makes measurable progress and preserves high-confidence identity evidence.

## Prerequisite Boundary

The backend/MLCore isolation boundary should be in place before dump hydration and enrichment work begins.

Interim serving contract:

```text
backend client
  sends provider-native seed IDs
shared MLCore
  resolves seeds to MLCore canonical IDs
  ranks in canonical ID space
  returns canonical recommendation IDs
backend client
  performs any vendor-specific output resolution it can handle locally
```

MLCore returning canonical IDs is acceptable until provider alias hydration is mature. The important boundary is that MLCore must not depend on model-local backend catalog IDs, and hydration jobs must enrich the shared MLCore graph rather than reintroduce local backend coupling.

## Current Shape

Current canonical item counts on Neptune (2026-06-22):

```text
recording_msid   120,150,287
recording_mbid    10,926,124
spotify_track              1
```

Current canonical aliases:

```text
listenbrainz:recording   112,431,541
musicbrainz:recording     10,924,175
isrc:recording              1,857,666
spotify:track                   171
```

## Desired Identity Graph

The graph should treat all external identifiers as evidence attached to canonical recordings:

```text
recording_msid:<msid>
  -> recording_mbid:<mbid>
  -> isrc:recording:<isrc>
  -> spotify:track:<id>
  -> spotify_uri:spotify:track:<id>
  -> future_provider:<id-or-uri>
```

The durable serving path should use local graph lookups:

```text
client provider ID
  -> MLCore canonical item
  -> candidate canonical items
  -> preferred output provider IDs
```

External APIs should be used by background jobs to grow the graph, not by the normal recommendation request path.

## Two Workstreams

### 1. Dump-Based Canonical and Platform Enrichment

Use MusicBrainz and ListenBrainz dumps to mine all locally available identity evidence:

- MSID -> MBID mappings
- MBID -> ISRC mappings
- ISRC values present in listens or metadata
- Spotify IDs/URLs present in ListenBrainz submissions
- Other platform URLs present in ListenBrainz submissions
- Spotify or streaming relationships present in MusicBrainz URL relationship data

This workstream should be storage-heavy but API-cheap. It should run mostly on cold storage and materialize compact graph outputs into hot storage.

### 2. External Spotify Resolution From ISRC

Use the current graph's ISRC aliases as an input queue. Resolve ISRCs into Spotify track candidates using Spotify Search, respecting rate limits and backoff. Store successful results back into the same identity graph.

This workstream should be API-quota-heavy but storage-light compared with dump ingestion. It can run indefinitely at a conservative rate.

#### Production execution contract

Spotify hydration is a resumable background projection. It never runs in a request
path and it never creates a second identity graph.

```text
hot:  canonical alias (source=isrc, status=active)
  -> cold: provider hydration item (lease, retry, latest evidence)
  -> Spotify Search: q=isrc:<normalized ISRC>, type=track, limit=10
  -> hot:  canonical alias (source=spotify, status=active)
  -> cold: provider hydration run (throughput and outcome counters)
```

The provider response must return the normalized query ISRC in
`track.external_ids.isrc`; search results that merely resemble the query are ignored.
Zero exact candidates become `no_match`, one becomes an active alias, and multiple
exact candidates or an alias already owned by another canonical item become
`ambiguous` for explicit reconciliation.

Only one worker may use the Spotify application credentials at a time. A PostgreSQL
advisory lock enforces this across hosts. Queue rows use expiring leases so an
interrupted worker can be replaced without losing work. Network and `5xx` failures use
bounded exponential backoff with jitter. A `429` honors `Retry-After`, pauses the whole
worker, halves its request rate, and preserves the item for retry. A `401` refreshes
the client-credentials token exactly once.

Production should assign this worker a dedicated Spotify application through
`SPOTIFY_HYDRATION_CLIENT_ID` and `SPOTIFY_HYDRATION_CLIENT_SECRET`. This prevents
interactive OAuth/catalog traffic from consuming the same app-level quota outside the
worker's limiter. The shared social-auth credentials remain a development fallback.

The initial production rate is one request per second. Spotify uses an
application-specific rolling 30-second limit and does not publish its exact value, so
raising this ceiling requires a bounded pilot with zero `429`s. Runtime metrics expose
backlog, outcomes, rate-limit count, accepted throughput, and observed-rate ETA.

#### Completion estimate

Spotify Search resolves one ISRC per request. Batching unrelated ISRCs into one search
would make completeness unverifiable because Search caps the returned track list. For
backlog `B`, sustained accepted rate `R`, and measured retry overhead `E`:

```text
requests = B * (1 + E)
seconds  = requests / R
```

Before subtracting already hydrated items, the current 1,857,666 active ISRC inventory
would take 43.0 days at 0.5 requests/s, 21.5 days at 1 request/s, 10.8 days at 2
requests/s, or 4.3 days at 5 requests/s without retries. These are capacity scenarios,
not quota claims. The bounded live pilot supplies accepted throughput and retry
overhead for the operational P50/P90 estimate. `no_match` outcomes are not retried
until a deliberate later source refresh.

## Canonical Merge Problem

MSID -> MBID is not just another alias insert if both identifiers already have separate canonical items. Example:

```text
listenbrainz:recording:<msid>  -> canonical_item A
musicbrainz:recording:<mbid>   -> canonical_item B
```

When we learn that `<msid>` and `<mbid>` represent the same recording, the graph needs a merge/redirect policy.

Recommended first implementation:

1. Add a canonical identity edge/redirect table:
   ```text
   from_canonical_item_id
   to_canonical_item_id
   relation=same_recording
   confidence
   source
   source_version
   status=active|conflict|retired
   evidence
   ```
2. Resolve through redirects at serving time.
3. Reassign aliases to the preferred canonical item only after coverage and conflict metrics look good.
4. Keep old canonical item IDs redirectable so existing model/training artifacts can be interpreted during transition.

Preferred canonical target:

```text
recording_mbid > spotify_track > recording_msid > catalog_track
```

## Storage Cost Model

Observed local reference point:

- `mlcore_canonical_item_alias`: about 67 GB for about 123.4M rows.
- Rough effective cost: about 0.54 KB per alias row including indexes.

Use this only as a planning approximation. Actual size depends on indexes, metadata JSON, fillfactor, and table bloat.

Estimated hot-storage growth:

| Artifact | Row Driver | Approx Size |
| --- | ---: | ---: |
| MSID->MBID redirect edges | up to mapped MSIDs, max 112.4M | 40-90 GB |
| ISRC aliases | unique canonical item/ISRC pairs | 5-60 GB |
| Spotify aliases | resolved Spotify track IDs | 5-60 GB |
| Hydration queue/attempt history | depends on retention | 5-100+ GB |
| Coverage snapshots/metrics | small | <5 GB |

Estimated cold-storage needs:

| Source | Current Known/Expected Size |
| --- | ---: |
| MusicBrainz `mbdump.tar.bz2` | 7,260,740,543 bytes (6.76 GiB) in `20260613-002047` |
| MusicBrainz derived dump | 476 MB compressed in 2026-06 full export |
| MusicBrainz edit history | 15 GB compressed, not needed for this plan |
| Expanded MusicBrainz staging | plan for tens to low hundreds of GB |
| ListenBrainz full listens dump | discover via manifest; likely very large |
| ListenBrainz extracted identity facts | depends on extraction, likely tens to hundreds of GB |

Keep raw dumps, extraction scratch, and staging tables in cold storage. Keep compact active aliases, redirect edges, and serving indexes in hot storage.

## Time Cost Model

Dump ingestion time is governed by disk throughput, decompression, JSON/CSV parsing, and index creation. It should be measured per source version and exposed in Grafana.

Spotify resolution time is governed by request count and sustained permitted request rate:

```text
duration_seconds = unresolved_isrc_count / sustained_requests_per_second
```

Or, if rate budget is expressed as requests per 30 seconds:

```text
duration_seconds = unresolved_isrc_count * 30 / requests_per_30_seconds
```

Runtime examples:

| ISRCs to resolve | 1 req/s | 10 req/s | 50 req/s | 100 req/s |
| ---: | ---: | ---: | ---: | ---: |
| 100K | 1.2 days | 2.8 hours | 33 min | 17 min |
| 1M | 11.6 days | 1.2 days | 5.6 hours | 2.8 hours |
| 10M | 116 days | 11.6 days | 2.3 days | 1.2 days |
| 100M | 3.2 years | 116 days | 23 days | 12 days |

Spotify does not publish a single fixed global limit. The job must adapt to `429` responses and `Retry-After`, and it should be configured to stay below observed limits.

## Progress Strategy

Do not optimize for "all or nothing." Optimize for compounding coverage:

0. Land and validate the backend/MLCore isolation boundary with canonical-only MLCore outputs.
1. Mine all local Juke and already-ingested data.
2. Ingest MusicBrainz for MBID->ISRC.
3. Ingest ListenBrainz dumps for MSID->MBID, ISRC, and platform URLs.
4. Attach high-confidence aliases and redirects.
5. Hydrate Spotify from ISRC with a conservative rate budget.
6. Prioritize items likely to be recommended.
7. Periodically re-run source dumps and incrementals.
8. Track coverage by whole catalog and by serving candidate set.

Whole-catalog coverage may remain incomplete for a long time. Serving-candidate coverage is the key operational metric.

## Paid Vendor Watchlist

Do not use paid vendor APIs in the first pass. Keep a watchlist for future comparison if Spotify quota or open-data coverage becomes the limiting factor:

- Music Story
- 7digital
- Gracenote
- Music APIs with ISRC/platform crosswalks

The design should make vendor data another provider evidence source, not a different identity system.

## Source Notes

- MusicBrainz full export `20260613-002047`, checked on 2026-06-13, listed
  `mbdump.tar.bz2` at 7,260,740,543 bytes. This core artifact contains the
  recording/ISRC/URL relationship tables required by the first bridge. The
  derived and edit-history dumps are not required for that import.
- ListenBrainz docs describe full dumps and incremental dumps, with listens stored as monthly JSON-lines files.
- Spotify Search supports `isrc` filters for tracks. Spotify rate limits are rolling-window based and return `429` when exceeded.
