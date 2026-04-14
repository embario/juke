# MLCore ListenBrainz Full Ingestion V3

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

## Recommended Next Experiment

Do not run another full pilot immediately.

Run these in order:

1. Identity-resolution verification against a real sample.
2. Small-scale finalize experiment on a bounded subset of already-loaded cold chunks.
3. Host-ownership fix for scratch artifacts.
4. Updated pilot with:
   - adaptive backpressure enabled
   - smaller cold finalize units
   - chunk-level Stage A metrics
   - verified nonzero resolution rate

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
