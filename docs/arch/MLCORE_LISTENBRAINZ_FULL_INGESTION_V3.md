# MLCore ListenBrainz Full Ingestion V3

## Status

As of `2026-04-22`, the V3 path has completed one production-scale full ListenBrainz ingestion successfully on Neptune for source version `listenbrainz-dump-2446-20260301-000003-full`.

That run proved:

- the canonical-item hot/cold schema is viable at full-dump scale
- the checkpointed full-ingestion engine can complete the end-to-end load
- the temporary scratch/load/stage workspace can be reclaimed after success

It also left a clear remaining focus:

- finalize throughput and operator ergonomics still need hardening so future runs are routine rather than hands-on

This document should now be read as a record of the design that got the first full run across the line, plus the remaining hardening targets for the next iteration.

## Goal

Turn the current v2 full-ingestion engine into a production-ready ListenBrainz loader that can complete a full dump on Neptune without making the host unpleasant to operate and without wasting a run on zero-resolution hot-path output.

This document exists because the v2 pilot extracted the right lessons:

- extract concurrency is now good enough to keep
- lean load tables are good enough to keep
- the provider lease is correct and should stay
- the current finalize step is still too monolithic
- identity resolution is currently failing to produce hot-path rows
- Stage A progress reporting is still too coarse for operators

## What The Pilot Proved

### Confirmed Good

- The archive-reader plus NVMe spool model is the right concurrency boundary for a single `tar.zst`.
- Process-based extract workers scale well on Neptune.
- Compact event chunk production works at the full-dump scale.
- Lean load tables are substantially better than the old JSONB-heavy staging path.
- Provider exclusivity prevents Celery and manual ingestion paths from contaminating a full run.

### Confirmed Bad

- The current finalize path still turns into one heavy PostgreSQL build step.
- The run moved all `128` partitions to `loaded`, but finalize sat in `CREATE TABLE ... AS` for over an hour with no rows committed to the final ledger.
- `rows_resolved = 0` and `session_rows_loaded = 0`, which means the current identity-resolution path is not producing useful hot-path output.
- Stage A metrics underreport useful progress while chunks are actively being written.
- Scratch cleanup is awkward because the ingestion artifacts are container-owned.

### Additional Findings From The Canonical-Item Pilot

The later canonical-item pilot established three more concrete facts:

- The canonical-item redesign fixed the hot-path identity problem.
  - full extraction produced nonzero canonicalized hot rows
  - session delta load worked
  - per-partition merge into hot/cold shadow tables worked
- The dynamic load-table schema must be treated as disposable runtime state.
  - the first canonical-item run failed because an older `mlcore_listenbrainz_event_load` table still existed without the new canonical-item columns
  - this was fixed by validating the load-table shape and dropping/recreating it when stale
- The final blocker is now pure finalize storage overlap.
  - the run completed partition extract, copy, and per-partition merge
  - it then failed while building final indexes/constraints on the hot shadow table with:
    - `psycopg2.errors.DiskFull`
    - hot tablespace OID `19519` (`juke_mlcore_hot`)

Measured peak storage during that run:

- scratch run root under `/srv/data/juke/full-ingestion/...`: about `564 GiB`
- `mlcore_listenbrainz_event_load`: about `429 GiB`
- `mlcore_listenbrainz_session_delta_load`: about `200 GiB`
- `mlcore_canonical_item`: about `50 GiB`
- `mlcore_listenbrainz_session_track_build`: about `307 GiB`
- hot filesystem `/srv/data` available at failure: about `165 GiB`

The immediate operational fix was to delete chunk/spool scratch before finalize. That recovered roughly `564 GiB` and proved scratch retention should not overlap with final index build.

The more important architectural lesson is:

- the current finalize path still materializes too many large hot-side structures concurrently
- even after scratch removal, replaying merge from load tables is still too slow to be the production approach

## V3 Changes

### 1. Fix Identity Resolution First

Before another large pilot, we need a narrow verification pass on the extractor's identity logic.

Required work:

- verify the current ListenBrainz parser is extracting the expected candidate identifiers from real rows
- measure candidate coverage separately for:
  - recording MBID
  - external Spotify ID
  - fallback Spotify track field
- add provider metrics for:
  - rows with MBID candidate
  - rows with Spotify candidate
  - rows with no usable candidate
  - rows resolved by match type

Reason:
The v2 pilot proving `0` resolved rows is a blocker for the hot `ListenBrainzSessionTrack` path. There is no point running a week-scale ingestion until that is corrected.

### 2. Add Adaptive Backpressure Instead Of Hard Stops

The next full-ingestion controller should reduce throughput under host pressure instead of treating pressure as a binary stop condition.

The pilot made this requirement clear:

- the host stayed safe
- SSH interactivity degraded anyway
- the useful operator action was not "kill the run immediately"
- the useful action was "make the run less aggressive"

#### Control Objective

Maintain host responsiveness and keep scratch growth bounded while still allowing the ingestion to make forward progress.

#### Primary Inputs

The controller should sample these signals on a fixed interval, for example every `15s`:

- NVMe `%util`
- `iowait`
- available RAM
- swap used and swap growth rate
- scratch bytes used under the active run root
- spool bytes currently on disk
- number of in-flight spooled members
- Stage A backlog
- Stage B backlog
- Stage C backlog

#### Primary Outputs

The controller should be allowed to change:

- `current_partition_workers`
- `current_load_workers`
- `current_finalize_parallelism`
- maximum in-flight spooled members
- whether Stage A is allowed to release additional work

#### Backpressure Order

Backpressure should apply in this order:

1. stop releasing new Stage A work
2. reduce extract worker budget
3. reduce load worker budget
4. reduce finalize parallelism

Reason:
Stage A is the easiest stage to pause cleanly, and it is the stage most likely to grow scratch aggressively. Finalize should already be narrowly bounded and should usually be the last thing to throttle.

#### Threshold Model

Use a soft/hard threshold model with hysteresis.

Recommended initial soft thresholds:

- NVMe `%util >= 75%`
- `iowait >= 12%`
- available RAM `<= 16 GiB`
- swap growth over the last window is positive
- scratch usage `>= 500 GiB`

Recommended initial hard thresholds:

- NVMe `%util >= 90%`
- `iowait >= 20%`
- available RAM `<= 8 GiB`
- scratch usage `>= 650 GiB`

#### Response Policy

On soft pressure for `3-5` consecutive samples:

- reduce Stage A release rate
- reduce `current_partition_workers` by `25%`
- reduce maximum in-flight spooled members

On persistent soft pressure:

- reduce `current_load_workers` by `1`
- pause new spooling until downstream catches up

On hard pressure:

- pause Stage A completely
- let Stage B and Stage C drain
- keep finalization alive unless it is the direct source of pathological pressure

On recovery for `10+` consecutive samples:

- increase budgets slowly
- restore at most one worker budget step per recovery window

The controller should never oscillate quickly. Hysteresis is required.

#### Operator Modes

V3 should support at least two policies:

- `throughput`
  - higher thresholds
  - best for unattended runs
- `interactive`
  - lower thresholds
  - best when Neptune needs to stay pleasant for SSH and other admin work

The default for this host should probably be `interactive`.

#### Why This Matters

This is the design change that turns "the host feels bad during a run" into a tunable runtime policy instead of an operator panic event.

### 3. Break Finalize Into Smaller Cold Units

The current finalize path still behaves like one giant cold-table materialization step.

V3 should finalize cold storage in bounded units instead of one large `CREATE TABLE AS` over the entire load table.

Recommended change:

- add one cold build table per partition or per partition group
- bulk-load and finalize those groups independently
- then attach or union them into the final cold table shape

Practical options:

- PostgreSQL declarative partitioning on the cold event ledger build path
- fixed partition-group build tables merged in a final metadata swap step

Why:
This gives us:

- smaller I/O spikes
- clearer progress checkpoints
- a less disruptive storage profile for the host
- a way to retry only the cold units that failed

### 4. Separate Cold Finalization From Hot Finalization

Hot and cold data should not share the same end-of-run finalize critical path.

V3 should:

- finalize cold event ledger build units first
- finalize hot session-track build units separately
- publish metrics for both paths independently

This matters because:

- cold storage is append-heavy and much larger
- hot storage is smaller but depends on working identity resolution
- when hot resolution is broken, we should still be able to assess cold-path throughput cleanly

### 4a. Replace Monolithic Hot Finalization With Two-Phase Hot Aggregation

This is the main redesign required by the latest run.

The current hot finalize still does too much at once:

- keep large session delta load tables alive in `pg_default`
- build a full replacement `mlcore_listenbrainz_session_track_build`
- build all final hot indexes on that replacement table
- hold existing live hot tables until the final swap

That overlap is what exhausted `juke_mlcore_hot`.

#### New Hot Finalize Strategy

Hot finalize should become a two-phase process:

1. provider-level partition merge into a narrow, append-only hot build heap
2. post-merge consolidation and final index build only after intermediate state has been collapsed

Recommended shape:

- `mlcore_listenbrainz_session_delta_load`
  - still receives per-partition deltas
- `mlcore_listenbrainz_session_track_stage`
  - narrow append-only heap keyed by:
    - `session_key`
    - `canonical_item_id`
    - `track_id`
    - `first_played_at`
    - `last_played_at`
    - `play_count`
- `mlcore_listenbrainz_session_track_build`
  - produced only after stage compaction

Instead of inserting directly from delta load into the final build table for every partition, V3 should:

- compact per-partition session deltas into a narrow stage heap first
- clear the consumed delta partition immediately
- once all stage data is present, run a single grouped compaction into the final hot build table
- only then create the final hot indexes

This reduces simultaneous hot overlap because:

- large partition delta tables are drained earlier
- stage heaps can stay minimally indexed
- the fully indexed final hot table exists only near the end

#### Resume Semantics

The current `--resume --force --execute-merge-stage` works, but it restarts hot merge from the beginning.

That is not acceptable for long-running production finalize.

V3 should persist explicit finalize checkpoints:

- `hot_stage_compacted = true|false`
- `cold_stage_compacted = true|false`
- `hot_indexes_built = true|false`
- `cold_indexes_built = true|false`
- `swap_completed = true|false`

Resume should restart from the last completed checkpoint, not replay the whole merge stage.

### 4b. Drop Scratch As Soon As Copy Completes

This is no longer optional.

The later run proved:

- scratch was about `564 GiB`
- scratch was not needed once load tables were fully populated
- deleting scratch before finalize materially changed available hot capacity

The engine should therefore:

- delete per-partition `events/` chunk directories immediately after successful copy
- delete `spool/` immediately after copy
- keep only:
  - manifest
  - control file
  - compact per-partition status manifests

This reduces hot overlap by hundreds of GiB before the expensive finalize step begins.

### 4c. Move Large Lean Load Tables Off `pg_default` Or Shorten Their Lifetime

The failed run showed that `pg_default` on `/srv/data` was still carrying:

- `mlcore_listenbrainz_event_load`: about `429 GiB`
- `mlcore_listenbrainz_session_delta_load`: about `200 GiB`
- `mlcore_canonical_item`: about `50 GiB`

That means hot/default storage is still overloaded even before shadow-table indexing finishes.

V3 should choose one of:

1. place load tables in a dedicated cold-adjacent transient tablespace
2. shorten load-table lifetime by draining them into smaller build units and deleting consumed units immediately

Recommendation:

- keep event load on cold/transient storage
- keep only the hot session stage on hot storage

The guiding principle is simple:

- cold facts should not occupy NVMe longer than necessary
- hot NVMe should be reserved for the minimum structures required to build the training table

### 5. Add Chunk-Level Stage A Metrics

The current Stage A operator surface is too delayed.

V3 should publish:

- chunk files written
- chunk bytes written
- spool bytes currently on disk
- active spool members
- extract worker backlog
- extract rows/sec over the last heartbeat window

That should be emitted continuously, not only when partition manifests are finalized.

### 6. Make Scratch Ownership Predictable

The pilot left behind container-owned chunk files that were awkward to remove from the host.

V3 should fix this operationally by one of:

- running the backend container as the host user/group for this path
- explicitly `chown`ing the scratch root at run start
- writing the ingestion artifacts through a helper that normalizes ownership

This is not a throughput issue, but it is an operator-quality issue and should be fixed before the next serious run.

### 7. Keep `merge_workers` As A Real Provider Knob

For ListenBrainz in v2, `merge_workers` is effectively a hint because finalize is still mostly one set-based operation.

V3 should make that knob real by giving providers a way to parallelize finalize across bounded cold units and hot units. Until then, the knob is only partially truthful.

### 8. Treat Runtime Load Tables As Disposable Schema

Runtime load tables are not migration-managed schema.

Therefore the engine must own their lifecycle completely:

- validate the expected column set before use
- drop/recreate stale load tables when the shape changed
- never assume `CREATE TABLE IF NOT EXISTS` is enough on a long-lived host

This is now required behavior, not a nice-to-have.

## Recommended Next Experiment

Do not run another full pilot immediately.

Run these in order:

1. Preserve the current run artifacts only long enough to extract size/row metrics from the load tables and build tables.
2. Implement hot finalize redesign:
   - narrow hot stage heap
   - early load-table drain
   - post-stage compaction into final hot build
   - checkpointed resume
3. Move or shorten cold load-table lifetime so large cold facts stop overlapping hot finalize.
4. Keep early scratch deletion as mandatory behavior.
5. Fix runtime load-table reconciliation everywhere the schema can drift.
6. Updated pilot with:
   - adaptive backpressure enabled
   - early scratch deletion
   - checkpointed finalize resume
   - nonzero canonical-item hot resolution
   - bounded hot overlap during index build

Only then run the next large pilot.

## Readiness Criteria For The Next Pilot

Before the next pilot starts, all of these should be true:

- sample-based resolution rate is nonzero and understood by candidate type
- adaptive backpressure is active and publishes its current mode and worker budgets
- finalize operates on bounded cold units, not one monolithic build
- chunk-level progress is visible during Stage A
- scratch cleanup does not require special host intervention
- the target tables are empty before launch

## Recommendation

The next iteration should focus on:

- correctness of hot-path resolution
- adaptive backpressure
- bounded cold finalization

Extract is no longer the weak point.
