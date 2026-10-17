---
id: mlcore-listenbrainz-incremental-import-redesign
title: Redesign the incremental ListenBrainz listen import around set-based dedupe
status: ready
priority: p3
owner: unassigned
area: platform
label: BACKEND/ML
complexity: 4
updated_at: 2026-10-17
---

## Goal

Make the incremental ListenBrainz listen import fast enough to keep up with new dumps, resumable, and idempotent, by replacing per-row dedupe lookups against the 1.75B-row ledger with batch, set-based dedupe (staging table plus merge or hash anti-join). This is item B9 in `docs/arch/MLCORE_IDENTITY_GRAPH_SATURATION_PLAN.md`; that plan only pauses the import and says it needs this separate redesign.

## Background

- Incremental `2669` (2026-09-20) imported 3.0M rows in about 9.4 days (~4 rows/s). The daily identity sync skips a version while its import runs, so identity was a no-op from Oct 7 and the newest processed listens were from Sep 2.
- The cause is random I/O on the HDD pool. Measured on Neptune: about 65 random index lookups per second, while the disks sat at ~92% utilisation with the import competing for them.
- Current flow (`backend/mlcore/ingestion/listenbrainz.py`, `import_listenbrainz_dump` → `_ingest_dump` → `_flush_batch`), per batch of 500 listens:
  1. In-memory dedupe within the batch (`seen_in_batch`).
  2. `ListenBrainzEventLedger.objects.filter(event_signature__in=signatures)`: ~500 random probes into the unique index on `event_signature` (32-byte, hash-random, so no locality, cold on HDD).
  3. `resolve_track_juke_id` (cached MBID lookups) and `bulk_ensure_canonical_items` (random lookups on `canonical_key`; also ~65/s class).
  4. `ListenBrainzEventLedger.objects.bulk_create`: random inserts into the `event_signature` unique index plus the `played_at`, `session_key`, `import_run`, `canonical_item`, `track` and `resolution_state` indexes.
  5. `_upsert_session_tracks`: select existing `(session_key, canonical_item_id)` rows (random probes into the 1.44B-row session-track table), then `bulk_create` and `bulk_update`.
  6. One transaction per batch, with a run-progress checkpoint (`_persist_run_progress`).
- So one batch costs on the order of 1,000+ random reads before any write; at ~65 reads/s that is the observed ~4 rows/s, regardless of CPU.
- `event_signature` is a content hash of the listen, so a re-imported dump produces identical signatures; dedupe is by exact membership, not ordering.

## Scope

Design first, then implement behind a flag so the old path stays available until the new one is proven.

1. **Staging and set-based dedupe.**
   - Parse a whole shard or large chunk (target 1–5M listens, configurable) into a per-run unlogged staging table (or sorted temp files loaded with `COPY`), with `event_signature` as a column.
   - Dedupe within staging with `DISTINCT ON (event_signature)` / sort.
   - Remove already-present events with one set-based anti-join against the ledger: `NOT EXISTS`/`LEFT JOIN … IS NULL` planned as a hash or merge anti-join. To avoid scanning all 1.75B rows each chunk, prune by a coarse key that the ledger can use sequentially, for example restrict to the `played_at` range of the chunk if a range scan on the `played_at` index is cheaper than probing (decide with `EXPLAIN` on a 1% slice; incremental dumps cover a narrow time window, so `played_at` is a candidate prune key). Document the chosen plan and the measured cost.
   - Alternative to evaluate: a sorted-merge against a bounded in-memory or on-disk Bloom/hash set of recent signatures, falling back to the anti-join only for hits. Keep the one with the best measured throughput and simplest correctness story.
2. **Set-based canonical resolution.** Resolve identities for the chunk's distinct keys (MBID, MSID, Spotify ID; see Phase 3 of the plan for the Spotify ID evidence change) with one join of distinct keys to the canonical item and alias tables, creating missing items in bulk, instead of per-batch probes. Do not change identity semantics here.
3. **Bulk merge.**
   - Insert the new ledger rows with one `INSERT … SELECT` (or `COPY` into the table) in event_signature-sorted order, to reduce random index writes. Consider building secondary-index work in bulk (sorted insert order helps only the unique index; evaluate deferring nothing on the live table, and say so if so).
   - Aggregate session-track facts in SQL (`GROUP BY session_key, canonical_item_id`) and merge with one `INSERT … ON CONFLICT (session_key, canonical_item_id) DO UPDATE` (min first, max last, summed `play_count`). Check the actual unique constraint on `ListenBrainzSessionTrack`; if the unique index does not exist, call that out as a migration question rather than adding one (see Out Of Scope).
   - Idempotency: the aggregate update must only count events that were actually inserted in this merge (derive session facts from the "new events" set, not from raw staging), so a rerun or partial rerun never double-counts `play_count`.
4. **Resumability.** Persist a checkpoint per completed chunk in the `SourceIngestionRun` metadata (shard origin, line/entry index, chunk id, counts), commit staging merge and checkpoint in one transaction, and key resumption on the existing fingerprint/resume-candidate logic. A crash mid-chunk must be safe to rerun: the anti-join makes the ledger insert idempotent, and the session merge in step 3 derives from the inserted set.
5. **Operability.** Progress and rate in the existing run metadata/progress callback (rows/s, chunk time by phase: parse, dedupe, resolve, merge); a management command or flags on the existing `replay_listenbrainz_incremental_task` path to run one incremental version with `--chunk-size`, `--resume`, and `--dry-run` (parse and dedupe against the ledger, report counts, write nothing).
6. **Interaction with other jobs.** The importer must expose a clean pause point (between chunks) so the operator can pause it for bulk identity phases (plan section 6), and must not hold a long transaction or lock the ledger across a chunk.

## Out Of Scope

- Changing identity semantics, Spotify ID extraction (plan Phase 3), or session-key derivation.
- Schema migrations on the 1.75B-row ledger or the 1.44B-row session-track table. If a unique index or column is needed, stop and raise it to the owner first; prefer designs that need none.
- Re-importing or repairing the already imported 3.0M rows of incremental `2669`; the design must make a rerun of that version safe, and the operator decides when to run it.
- Running anything on Neptune. The fleet does not deploy or run management commands against `/srv/juke-dev`; a separate operator session does.
- Moving tablespaces to NVMe (plan section 6 covers that).

## Acceptance Criteria

- A written design in this file's Handoff (or an `docs/arch/` addendum) with the chosen dedupe strategy, the `EXPLAIN` evidence from a 1% slice on realistic data (provided by the operator), and the expected rows/s.
- Unit tests with small fixtures (a few hundred listens, no MLCore-heavy jobs):
  - A dump containing duplicates within the dump, duplicates of ledger rows, and new rows imports only the new rows once.
  - Re-running the same dump imports zero rows and leaves `ListenBrainzSessionTrack.play_count` unchanged.
  - Interrupting after the staging load or after the ledger insert but before the checkpoint, then resuming, yields exactly the same ledger and session-track state as an uninterrupted run.
  - Output parity: for the same fixture, the new path produces the same ledger rows and session-track aggregates as the current `_flush_batch` path.
- A query-count/plan check proves the new path does not issue per-row (or per-500-row `IN`) ledger lookups: the number of ledger queries per chunk is constant, independent of chunk size.
- The old row-by-batch path remains available behind a setting until the operator confirms the new one.
- The PR description tells the operator exactly how to run it on Neptune: command and flags, expected duration at the measured rate for a typical incremental, how to pause between chunks, and how to resume after a stop or crash.
- Backend tests pass in CI.

## Execution Notes

- ASYNC: this task file defines the work; proceed after reading the plan. Ship in two PRs if large: (a) set-based dedupe plus ledger merge behind a flag, (b) set-based canonical resolution and session-track merge.
- Key files: `backend/mlcore/ingestion/listenbrainz.py` (`import_listenbrainz_dump`, `_flush_batch`, `_upsert_session_tracks`, resume helpers), `backend/mlcore/models.py` (`ListenBrainzEventLedger`, `ListenBrainzSessionTrack`, `SourceIngestionRun`), `backend/mlcore/tasks.py` (`replay_listenbrainz_incremental_task`), `backend/mlcore/services/listenbrainz_source.py` (remote sync), `backend/mlcore/services/incremental_identity.py` (skips versions whose import is running), `backend/mlcore/services/canonical_items.py` (`bulk_ensure_canonical_items`).
- Plan reference: `docs/arch/MLCORE_IDENTITY_GRAPH_SATURATION_PLAN.md` sections 2.3 (stalled import), 6 (I/O budget: "every bulk phase must be set-based hash or merge joins, never nested-loop index probes") and B9.
- Risks:
  - An anti-join against 1.75B rows can itself be a long scan on HDD; the `played_at`-range prune (or an equivalent) is what makes it proportional to the chunk, so validate the plan before relying on it.
  - Sorted bulk inserts help the unique index only; the other secondary indexes still take random writes. Measure before promising a speedup, and report per-phase timing.
  - Double counting in `play_count` on partial reruns if session aggregates are derived from staging instead of the inserted set.
  - Large transactions bloat WAL and hold locks; keep chunk size bounded and the merge one short transaction.
  - Unlogged staging data is lost on crash: resumability must rely on the committed checkpoint, not on staging contents.
- Commands (operator, on Neptune, to be finalised in the implementing PR): none yet.

## Handoff

- Completed: Task written from the plan (PR #250 version) and a read of the importer; no code changed. The existing code already batches 500 signatures per `IN` query, but each is still ~500 random index probes, which is why batching alone did not help.
- Next: Capture a 1% slice `EXPLAIN` for the candidate anti-join (operator), then implement PR (a). The importer's old path stays behind a flag.
- Blockers: None. Raise any needed migration to the owner before writing one.
