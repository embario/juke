---
id: mlcore-identity-graph-saturation
title: Saturate the MLCore identity graph with Spotify, ISRC, and MBID evidence from local ListenBrainz and MusicBrainz data
status: in_progress
priority: p1
owner: fleet
area: platform
label: BACKEND/ML
complexity: 5
updated_at: 2026-10-17
---

## Goal

Attach Spotify track IDs, ISRCs, and MBIDs to the canonical items that co-occurrence already uses, using only data on Neptune (ListenBrainz shards, MusicBrainz bridge tables), with no Spotify API calls and within Neptune's disk limits. Full strategy, measurements, and disk budget: `docs/arch/MLCORE_IDENTITY_GRAPH_SATURATION_PLAN.md`.

## Scope

- Phase 0 (owner decisions): snapshot policy for the database tablespaces, NVMe scratch/temp tablespace, pausing the incremental listen import during bulk phases, serving redirect-chain fix.
- Phase 1: read-only measurement (evidence profile across sampled months; MusicBrainz Spotify-URL overlap driven from the recordings side; play-weighted coverage baseline).
- Phase 2: MusicBrainz Spotify track URLs to aliases (absorbs `mlcore-spotify-aliases-from-dump-evidence`).
- Phase 3: extraction schema v3: per-shard MSID-Spotify and MSID-ISRC pairs with observation counts; fix ingestion so new listens keep Spotify IDs as evidence.
- Phase 4: many-to-many evidence table (cold).
- Phase 5: cluster MSIDs by dominant Spotify ID; choose MBID or new `spotify_track` target; flat redirects; aliases on final targets.
- Phase 6: ISRC saturation, including MSID-to-MBID via unique MusicBrainz ISRC.
- Phase 7: hydration queue integration and play-weighted coverage metrics.
- Phase 8: keep current through the incremental pipeline and new MusicBrainz releases.

## Out Of Scope

- Spotify API calls (the hydration worker is paused; account quota is shared with sign-in).
- Deleting or dropping any data, or changing ZFS snapshots, without explicit owner approval (section 4.3 of the plan lists candidates).
- Redesigning the incremental listen import (flagged as a separate problem).
- Retraining co-occurrence (not needed: serving maps through redirects).
- Popularity priority for API hydration (fleet task `spotify-hydration-adaptive-budget-and-popularity-priority`).

## Acceptance Criteria

- Phase 1 numbers recorded in Handoff before any write; estimates in the plan's section 4.2 updated.
- Tests: Spotify ID/URL normalisation (bare IDs, `spotify:track:`, `open.spotify.com/track/`, `intl-xx/`, query strings, album/artist rejection); extraction with counts and schema-v3 replay; evidence idempotency; dominant-ID rule; group targeting (one MBID, MusicBrainz URL, ISRC bridge, new `spotify_track`, multi-MBID conflict); never overwriting active redirects or aliases owned elsewhere; flat redirects (no chains longer than one hop); group-size cap.
- Serving: a test showing a seed reaches co-occurrence neighbours through every redirect in its cluster.
- On Neptune: aliases, redirects, and evidence rows created match Phase 1 within expected conflict losses; play-weighted MBID/ISRC/Spotify coverage reported before and after; zero Spotify API requests from this work; disk usage within the plan's budget (persistent ~20-30 GB physical HDD, scratch ≤50 GB NVMe).
- Backend tests pass in CI.

## Execution Notes

- ITERATIVE: Phase 0 needs owner decisions; Phase 5 merge rules need a sample audit before bulk activation. Phases 1-4 can run autonomously once Phase 0 is settled.
- Key files: `backend/mlcore/services/listenbrainz_identity_bridge.py` (extractor, staging, materialisation patterns), `backend/mlcore/ingestion/listenbrainz.py` (`_extract_spotify_id`, `SPOTIFY_ID_KEYS`), `backend/mlcore/services/canonical_items.py` (`identity_from_listenbrainz_candidates`), `backend/mlcore/services/musicbrainz_bridge.py`, `backend/mlcore/services/musicbrainz_isrc_aliases.py`, `backend/mlcore/services/canonical_redirects.py`, `backend/mlcore/services/provider_hydration.py`, `backend/recommender_engine/app/main.py` (`_COOCCURRENCE_SQL`, `_RESOLVE_ALIASES_SQL`), `backend/mlcore/models.py`.
- Coordination: the fleet is editing `provider_hydration.py` and `hydrate_spotify_from_isrc.py` (Part 2). Keep Phases 1-6 in new modules and commands; take Phase 7 after Part 2 lands.
- Resource notes: the HDD pool is IOPS-bound (~130 reads/s per disk observed). Use NVMe for scratch; schedule bulk phases with the incremental import paused; batch all writes; run large read-only checks as samples.
- Risks: wrong merges from community data (mitigated by dominance, group cap, conflict-never-overwrite, sample audit); snapshot pinning of transient data (mitigated by NVMe scratch); one-hop serving expansion (mitigated by flat redirects plus serving fix); Spotify Developer Policy III.14 depending on MLCore's use of provider IDs (owner judgement).

## Handoff

- Completed: overnight read-only investigation (2026-10-16/17): storage and snapshot audit, table inventory, identity graph counts, evidence profile of a full month, pipeline timings, code-path review. Written up in the plan doc.
- Next: owner decisions in plan section 8; then Phase 1.
- Blockers: Phase 0 decisions.
- B4 (evidence table + loader): `mlcore_identity_evidence` and `load_identity_evidence` (`mlcore/services/identity_evidence.py`); loads the schema-v3 shard files per scheme in groups, set-based, resumable. Operator instructions are in the PR description.

### B6 execution (2026-10-17, Codex implementer-1)

- Status: in progress; ASYNC, owner-authorized Track B B6 only. Refs #249.
- Goal/scope: set-based dominant-Spotify clustering from B4 evidence; MBID/URL/unique-ISRC targeting, cap 200, flat redirects using B7's shared writer, conservative aliases, deterministic whole-group sampling, bounded audit/review exports, dry-run default, resumable batches and EXPLAIN tooling.
- Out of scope: Neptune execution/deployment, API calls, full-run authorization, B7's independent ISRC bridge, #177/master.
- Acceptance: small PostgreSQL fixtures cover dominance, targeting and conflicts, group cap, active redirect/alias protection, flat promotion, sampling, dry-run, audit and replay. CI green; normal reviewer/integrator pipeline with needs-review/P2/author:codex. Operator instructions include 1% audit (~200 merges), owner approval before full run, flags, timing and resume.
- Risks: evidence can change between resume attempts (operator freezes ingestion); shared writer dependency must land before B6; full scans cost hours even for a small sample. Never use per-row database lookups.
- Handoff: implementing in `juke-app/mlcore-spotify-clusters`; B7 shared writer currently being prepared in `juke-app/mlcore-isrc-bridge`.

- B6 validation: 19 PostgreSQL small-fixture tests pass locally (isolated PG14/Django5.2, no Docker or Neptune). Main staging EXPLAINs force sequential/hash joins; lint passes. B7 #258 supplies the shared writer; B6 must merge after it. Operator commands and limitations are in `docs/arch/MLCORE_SPOTIFY_CLUSTER_RUNBOOK.md`.

### B7 follow-up review fixes (2026-10-17)

- ASYNC, owner-authorized follow-up to #258; Refs #230. Address all three P1 and three P2 post-merge findings before operator activation.
- Scope/acceptance: validate whole clusters before root sampling; veto contradictory/ineligible members; require approval above an effective 1% sample (including resume); persist exact counts; export contributing MSID/mapping provenance; preserve run-bound audit selection across pause/resume and checkpoint failures. Add PostgreSQL regression fixtures for each finding and EXPLAIN the insert/repoint statement.
- Out of scope: Neptune commands/deployment, Spotify calls, full-run approval, unrelated B6 behavior. Preserve set-based joins, never-overwrite edges and flat redirects.
- Validation: focused local PG14 suites (Docker forbidden on Uranus), lint and CI. Risk: full evidence staging costs remain even at 1%; freeze competing graph/evidence writers for run/resume.
- Handoff: all six findings implemented on `juke-app/mlcore-isrc-bridge-fixes`; 61 focused PG14 tests pass (B7, B6, B4, B5), Ruff and diff checks pass. Actual insert/repoint EXPLAIN uses sequential/hash joins. Audit selection is stored before writes; each checkpoint commits with its batch; saved audits can be exported without staging. Algorithm v2 deliberately rejects v1 resume. Member provenance is bounded to 10 MSIDs per audited root (limit included in CSV). PR/review pending; no Neptune execution.
