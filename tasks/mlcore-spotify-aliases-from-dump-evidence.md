---
id: mlcore-spotify-aliases-from-dump-evidence
title: Spotify track aliases from MusicBrainz and ListenBrainz dump evidence (no Spotify API calls)
status: ready
priority: p1
owner: unassigned
area: platform
label: BACKEND/ML
complexity: 4
updated_at: 2026-10-16
---

## Goal

Create Spotify track aliases (`source=spotify, resource_type=track`) from evidence MLCore already holds in local dumps, so the Spotify hydration worker never calls the Spotify API for those items. This finishes the platform-ID half of `mlcore-listenbrainz-msid-mbid-platform-dump-enrichment` (in_progress) and the unconsumed provider-URL output of `mlcore-musicbrainz-isrc-bridge-ingestion` (review).

## Why now

- The hydration app shares one Spotify development-mode quota with the login/playback app (quota is per developer account since July 2026). On 2026-10-16 the hydrator received `QUOTA_EXCEEDED` with an ~18.5 h cooldown after ~513 requests in the window. API hydration cannot be scaled up safely, so every item resolved offline is quota returned to users.
- Backlog on Neptune (2026-10-16): 6,413,153 pending, 316,337 matched, 142,751 ambiguous, 109,190 no_match, 5,211 dead.

## What exists today (verified 2026-10-16)

- **MusicBrainz:** `mlcore_musicbrainz_recording_url` (cold) holds 1,735,716 `provider='spotify'` rows across two source versions (`20260613-002047`, `20260627-002124`). 1,735,170 are `open.spotify.com/track/...` URLs covering 812,941 distinct recording MBIDs; 366 album, 34 artist, 146 other. Link type is almost entirely `free streaming`. **Nothing reads this table**; it is written and tested only (`backend/mlcore/services/musicbrainz_bridge.py`).
- **ListenBrainz:** the identity extractor (`backend/mlcore/services/listenbrainz_identity_bridge.py::_extract_identity_pairs`) emits only MSID->MBID and MSID->ISRC pairs. `spotify_id`, `origin_url`, and `music_service` in `track_metadata.additional_info` are not extracted. `backend/mlcore/ingestion/listenbrainz.py::_extract_spotify_id` already parses these keys, but only to resolve listens to existing `Track` rows during event ingestion; it creates no aliases.
- MBID aliases are `source=musicbrainz, resource_type=recording, source_id=<recording_mbid>`. Hydration items join to canonical items via `canonical_item_id`.

## Scope

### Phase 0: Measure (read-only, do first)

- Count pending/ambiguous/no_match hydration items whose canonical item has an MBID alias with a Spotify **track** URL in `mlcore_musicbrainz_recording_url` (latest source version). Report overlap and how many of those recordings have more than one Spotify track URL.
- Count ListenBrainz `spotify_id` / Spotify `origin_url` coverage. Prefer a bounded sample of recent monthly listen files (the full dump is 159 GB and ordered oldest first) over a full scan.
- Record numbers in Handoff before writing any aliases. Stop and report if overlap is negligible.

### Phase 1: MusicBrainz Spotify URLs -> aliases

- Management command + service that, for the latest MusicBrainz source version, parses Spotify track IDs from URLs (handle `intl-xx/` paths, query strings, `spotify:track:` URIs; validate 22-char base62).
- Resolve recording MBID -> canonical item through the existing alias and `mlcore_canonical_item_redirect` paths.
- Exactly one Spotify track ID per recording: upsert an active alias with `metadata.match_source='musicbrainz_url'`, `source_version`, link type, and URL. Several IDs per recording: do not activate; count as ambiguous (optionally store as non-active evidence).
- Conflict-aware: if the Spotify ID is already aliased to a different canonical item, skip and count (same rule as `hydrate_spotify_item`). Never overwrite an existing alias.
- Mark the matching `ProviderHydrationItem` rows `matched` with evidence `{"resolved_by": "musicbrainz_url", ...}` so the worker skips them. Do not touch `running` (leased) items.
- Batched and resumable; no full-table locks; must not block `claim_hydration_item`. Album/artist URLs are ignored.

### Phase 2: ListenBrainz Spotify IDs -> aliases

- Extend the shard extractor (same pass as MSID->MBID/ISRC) to emit MSID->Spotify track ID pairs from `additional_info.spotify_id`, Spotify `origin_url`, and similar keys (reuse `_extract_spotify_id`; add a shared URL/ID normalizer with Phase 1).
- Bump the extraction schema version so previously succeeded shards replay once (the mechanism already used for ISRC).
- Aggregate per (MSID, Spotify ID) with observation and distinct-shard counts; treat as submitted evidence, not truth. Activate only clean pairs (one Spotify ID per resolved canonical item, or a dominance rule like `shard-dominance-v1`), conflict-aware as in Phase 1.
- Wire into `ingest_incremental_identity` so new deltas keep contributing.

### Phase 3: Hydrator integration

- Seeding (`seed_spotify_hydration_queue*`) skips canonical items that already have an active Spotify track alias.
- Metrics: aliases created by source (`musicbrainz_url`, `listenbrainz`), items resolved offline, conflicts, and multi-ID ambiguities, in the existing textfile/Grafana path.

## Out Of Scope

- Any Spotify API calls, including verifying offline-derived IDs against Spotify.
- Changing API hydration pacing/quota logic or Part 2 popularity priority (fleet task `spotify-hydration-adaptive-budget-and-popularity-priority`).
- Re-deciding existing `matched`/`ambiguous` outcomes from API hydration.
- Apple Music/Deezer/Tidal aliases (the same table holds them; a follow-up can reuse the normalizer).

## Acceptance Criteria

- Phase 0 numbers recorded in Handoff before any write.
- Unit tests: Spotify URL/URI/ID normalization (intl paths, query strings, invalid IDs, album/artist rejection); one-ID vs multi-ID recordings; existing alias to a different canonical item is skipped; redirects resolved; idempotent re-run creates nothing new; leased items untouched.
- ListenBrainz extractor tests: Spotify ID pairs extracted alongside MBID/ISRC, schema-version replay happens once, incremental replay idempotent.
- On Neptune: aliases created and hydration items marked matched, with counts matching Phase 0 within expected conflict/ambiguity losses; the worker's backlog metric drops accordingly; zero Spotify API requests attributable to this job.
- Backend tests pass in CI.

## Execution Notes

- ASYNC for Phases 0-1 (well-defined, local data only); ITERATIVE for Phase 2 (confidence rules need real-data review).
- Key files: `backend/mlcore/services/musicbrainz_bridge.py`, `backend/mlcore/services/listenbrainz_identity_bridge.py`, `backend/mlcore/ingestion/listenbrainz.py` (`_extract_spotify_id`, `SPOTIFY_ID_KEYS`), `backend/mlcore/services/provider_hydration.py` (seeding, `_finish_item`), `backend/mlcore/models.py` (`MusicBrainzRecordingURL`, `CanonicalItemAlias`, `ProviderHydrationItem`, `CanonicalItemRedirect`).
- Coordination: the fleet is editing `provider_hydration.py` and `hydrate_spotify_from_isrc.py` for Part 2. Keep Phases 0-2 in new modules/commands; take Phase 3 seeding changes after Part 2 lands, or coordinate.
- Resource notes: the alias table is hot and large; batch writes (e.g. 10k) and run on Neptune off-peak. Raw dumps stay cold.
- Risks:
  - MusicBrainz Spotify links are community-entered; some point to the wrong recording or a regional duplicate. Mitigated by conflict checks and single-ID rule; spot-check a sample before bulk activation.
  - Spotify relinking/regional IDs: one recording can legitimately have several Spotify IDs. These stay non-active rather than guessed.
  - Developer Policy: these aliases are Spotify identifiers used for playback linkage. If MLCore uses Spotify-derived data for model training, Developer Policy III.14 applies regardless of source. Owner to confirm use.

## Handoff

- Completed: plan drafted from code reading and read-only Neptune queries (2026-10-16). A Phase 0 MusicBrainz overlap query (1% `TABLESAMPLE` of hydration items, correlated `EXISTS` through the alias table into `mlcore_musicbrainz_recording_url` with a `::text` cast on `recording_mbid`) hit its 300 s statement timeout without a result. For Phase 0, drive from the smaller side instead: distinct Spotify-track recording MBIDs (~813k) -> alias lookup by `(source, source_id)` -> hydration items by `canonical_item_id`. Check the alias table's indexes first, and run in batches.
- Next: run Phase 0 and record numbers; then Phase 1.
- Blockers: none. Not yet added to `tasks/_index.md` (fleet is working in the same worktree; add when committing).
