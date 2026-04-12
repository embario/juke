# MLCore ListenBrainz Rebuild Throughput Redesign

## Goal

Redesign the ListenBrainz full-rebuild ingestion path so Neptune can complete a fresh shard materialization and database load in one week or less, with reliable progress checkpoints and without depending on the current slow Celery shard-import loop.

## Why The Current Path Is Not Good Enough

The current implementation is optimized for correctness and resumability, not for one-off full rebuild throughput.

Observed state on Neptune on 2026-04-11 / 2026-04-12:

- Host resources:
  - 32 CPU cores
  - 60 GiB RAM
  - hot NVMe storage at `/srv/data`
  - cold HDD/ZFS storage at `/srv/data/backups`
- ListenBrainz full dump:
  - archive path: `/srv/data/backups/juke/listenbrainz/full/listenbrainz-listens-dump-2446-20260301-000003-full.tar.zst`
  - compressed size: about `149 GiB`
  - currently materialized monthly shard tree size: about `395 GiB`
  - total uncompressed bytes recorded in the shard manifest: `945,529,223,501`
  - monthly shard count: `261`
  - largest shard: `listens/2026/1.listens` at `11,117,097,626` bytes
- Sample shard estimates:
  - average bytes per row from a 200k-row sample of `2026/1.listens`: about `587-591` bytes
  - estimated rows in that shard: about `18.9M`
  - raw Python parse + hashing sample on that shard: about `74.5k rows/sec` on one core
- Live reliability observation:
  - the current direct full import was left in `running` state with no active DB session and no progress after `2026-04-11T20:32:31Z`

Using the sampled bytes-per-row, the full dump is roughly `1.6B` listens. To finish within seven days, the system needs sustained end-to-end throughput around:

- `1.6B / 7 days ~= 2,650 rows/sec`

That target is not extreme for Neptune. The problem is not raw JSON parsing speed. The problem is the architecture around parsing and writes.

## Current Bottlenecks

### 1. ORM-heavy ingestion

The current full-import path still uses Django ORM row objects for the hot path:

- event-ledger rows are built in Python and inserted with `bulk_create`
- session-track rows are resolved, aggregated, fetched, and updated through ORM queries
- progress is persisted back into `SourceIngestionRun` after every batch

This introduces avoidable Python object churn, ORM overhead, and transaction churn.

### 2. Tiny batch size and per-batch duplicate queries

Current defaults:

- batch size: `500`
- every batch checks `ListenBrainzEventLedger` for existing event signatures
- every batch also queries `ListenBrainzSessionTrack` for existing `(session_key, track_id)` rows

That is the wrong shape for a fresh empty rebuild. On a fresh rebuild:

- there is no prior data to dedupe against
- the expensive per-batch existence checks buy very little
- the database is forced into constant small write transactions

### 3. Track resolution is still database-driven

Track resolution currently happens through `IdentityResolver` / ORM lookup logic during import. That is acceptable for incremental imports, but it is too expensive for a one-off billion-row rebuild.

For a full rebuild, the identity map should be materialized once and then used from memory or a local fast key-value lookup structure.

### 4. Session-track upserts are row-oriented

The compact schema is correct, but the write path is still too row-oriented:

- aggregate in a Python dict
- query existing rows for current batch keys
- create or update through ORM

For the full rebuild, session-track updates need to be staged and merged set-wise, not batch-by-batch through ORM.

### 5. Celery orchestration is the wrong control plane for the rebuild

Celery is useful for:

- recurring incrementals
- scheduled remote sync
- bounded operational jobs

It is a poor fit for a one-off, multi-day, high-throughput rebuild because:

- task-state persistence is indirect
- stale `running` tasks are easy to end up with
- task fan-out is shaped around queue slots, not around full-machine saturation
- restart semantics are more complicated than necessary

### 6. Monthly shards are not the right execution unit

Monthly shards are useful for archival organization, but they are poor execution units:

- shard sizes are badly skewed
- large recent months are around `8-11 GiB` each
- small early months are tiny
- the work distribution is uneven

The full rebuild should use fixed-size execution partitions, not monthly calendar boundaries.

## Redesign Principles

### Separate full rebuilds from incremental imports

The full rebuild path should be a dedicated ingestion engine with different tradeoffs:

- optimize for throughput first
- accept larger working sets
- minimize ORM usage
- use direct database bulk load primitives

Incremental imports can keep the slower but simpler resumable logic.

### Treat Neptune as a batch-processing host

This host has enough resources to run the rebuild as a dedicated batch job:

- reserve most of the 32 cores for ingestion
- use hot NVMe for intermediate work products
- keep cold HDD for the source archive and cold final tablespace

This should not be designed like a small always-on background task.

### Prefer idempotent partitions over row-by-row resume

Recovery should happen by partition, not by partial ORM cursor state inside one Python process.

## Proposed New Architecture

The new full rebuild path should be a three-stage pipeline.

### Stage A: Stream and repartition

Input:

- the full `.tar.zst` archive on cold storage

Output:

- a hot-storage working directory under NVMe
- `N` fixed-size partition files for event-ledger rows
- `N` fixed-size partition files for session-track deltas

Mechanics:

- run a dedicated rebuild command outside Celery
- stream the archive once
- parse JSON lines in a multi-process pipeline
- resolve track IDs from an in-memory identity map
- compute:
  - `event_signature`
  - `session_key`
  - `track_id`
  - `resolution_state`
- route each row into a partition based on a stable hash:
  - event ledger partition by `hash(event_signature) % N`
  - session-track partition by `hash(session_key, track_id) % N`

Why:

- partitions become evenly sized regardless of month skew
- recovery can restart at the partition level
- later DB load steps can run independently

Recommended starting point:

- `N = 128` or `256`

At `128` partitions, the average partition is about `7.4 GiB` uncompressed by manifest bytes.

### Stage B: Bulk load into unlogged staging tables

For each partition:

- generate PostgreSQL `COPY`-ready delimited files or binary `COPY` streams
- load into unlogged staging tables

Suggested staging tables:

- `mlcore_lb_event_ledger_stage`
- `mlcore_lb_session_track_stage`

Suggested staging-table properties:

- unlogged
- no secondary indexes during load
- minimal constraints during initial ingest

Why:

- `COPY` is dramatically cheaper than ORM object creation
- unlogged staging minimizes WAL pressure
- loading into staging isolates failures and supports per-partition restart

### Stage C: Set-based merge into final tables

After a partition is loaded into staging:

- merge event rows into `mlcore_listenbrainz_event_ledger`
- merge session-track aggregates into `mlcore_listenbrainz_session_track`

For a fresh empty rebuild, the fastest path is:

1. create final tables without the heavyweight secondary indexes
2. load all data
3. create indexes after the load
4. analyze the tables

That is materially faster than maintaining all indexes row-by-row during load.

If some uniqueness enforcement must remain during load:

- keep only the minimum required uniqueness index
- build the rest afterward

## Identity Resolution Redesign

### Current problem

Track resolution is still effectively ORM-shaped and repeated inside the ingest loop.

### Proposed approach

Before Stage A starts, build immutable lookup maps:

- `recording_mbid -> track_juke_id`
- `spotify_id -> track_juke_id`

Options:

1. Load both maps into Python dictionaries once per worker process.
2. Materialize them into a local SQLite or LMDB key-value store on NVMe and open read-only in workers.

Recommendation:

- start with Python dictionaries if the catalog cardinality fits comfortably in memory
- fall back to LMDB if process duplication becomes too expensive

On Neptune, memory is not the first constraint. Simplicity matters more than premature complexity.

## Session-Track Redesign

The current compact schema is right, but the write path should change.

For the full rebuild:

- aggregate `(session_key, track_id)` within each partition before database load
- write one delta row per unique `(session_key, track_id)` in that partition
- load those deltas with `COPY`
- merge them into the final hot table with one set-based statement per partition

This avoids:

- repeated ORM fetches
- repeated row-level `bulk_update`
- repeated small updates against the unique key

## Control Plane Redesign

### Full rebuilds

Do not run the full rebuild via Celery task fan-out.

Use a dedicated management command, for example:

- `python manage.py rebuild_listenbrainz_full`

This command should:

- own the entire pipeline
- manage process pools directly
- checkpoint by partition
- emit a durable progress manifest on disk
- resume from completed partition markers

### Incrementals

Keep Celery for:

- scheduled remote sync
- small incremental replay
- operational backfills that do not saturate the whole machine

This gives the project two engines:

- batch rebuild engine
- operational incremental engine

That split is correct.

## Recommended Neptune Resource Budget

For the dedicated full rebuild:

- parser / partition workers: `16`
- load / merge workers: `4-8`
- reserved DB/OS headroom: leave `6-8` cores unassigned
- working memory target: `20-30 GiB`
- NVMe scratch root: under `/srv/data/juke/listenbrainz-rebuild`

This is intentionally much more aggressive than the current worker design.

## Target Throughput Model

Conservative planning target:

- full rebuild size: `~1.6B` listens
- deadline: `<= 7 days`
- required sustained throughput: `~2.65k rows/sec`

Observed single-core parser sample:

- `~74.5k rows/sec`

Implication:

- raw parse/hashing is not the limiting factor
- database write shape, dedupe strategy, and control-plane reliability are the real problems

If the new pipeline can sustain even:

- `5k rows/sec` end-to-end

then a `1.6B` row rebuild finishes in about:

- `3.7 days`

That leaves enough headroom for retries, index builds, and validation.

## Concrete Implementation Plan

### Phase 1: Benchmark and instrumentation

- add a benchmark helper for `.listens` shard parse throughput
- add partition-level throughput logging
- add durable on-disk rebuild progress manifests

### Phase 2: New full rebuild engine

- implement dedicated `rebuild_listenbrainz_full` command
- build identity-map preloader
- implement archive stream -> hash partition pipeline
- emit `COPY`-ready partition files on NVMe

### Phase 3: Bulk-load path

- add unlogged staging tables
- add `COPY` loaders
- add set-based merge SQL for event ledger and session-track deltas
- move secondary index creation to post-load when rebuilding from empty DB

### Phase 4: Cutover policy

- reserve current Celery path for incrementals only
- use new rebuild engine for fresh full imports
- keep the old path behind a fallback flag until the new engine is proven

## Ideas Explicitly Rejected

### 1. Simply increase Celery worker count

Rejected because the current bottlenecks are architectural, not just concurrency-related. More Celery workers would increase contention without fixing ORM-heavy writes or control-plane fragility.

### 2. Keep monthly shards as the primary execution unit

Rejected because the shard sizes are too uneven and recent months dominate runtime.

### 3. Optimize only the Python parser

Rejected because parser throughput is already far above the seven-day minimum target on one core.

### 4. Continue querying the final tables for duplicates during a fresh rebuild

Rejected because a fresh rebuild into empty tables should not pay that cost on every tiny batch.

## Acceptance Criteria For The New Engine

The redesign should be considered successful when:

- a full rebuild can be launched from one dedicated command
- restart/resume happens by partition, not by partial ORM state
- the engine sustains enough end-to-end throughput to finish within seven days on Neptune
- the final data lands in:
  - `juke_mlcore_hot`
  - `juke_mlcore_cold`
- operational progress is visible without depending on Celery task state

## Immediate Next Step

Implement the dedicated rebuild command and staging-table path tracked in GitHub issue `#127`.
