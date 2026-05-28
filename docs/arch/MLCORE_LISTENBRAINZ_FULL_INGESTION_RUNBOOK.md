# MLCore ListenBrainz Full Ingestion Runbook

This runbook documents the operational path for a full ListenBrainz ingestion on Neptune after the v2/v3 hardening work.

## Purpose

Use this workflow when:

- starting a new ListenBrainz full ingestion
- resuming an interrupted run
- adjusting runtime throttle policy
- verifying that finalize and cleanup completed correctly
- confirming the resulting canonical-item hot dataset is ready for training

## Preconditions

- `backend`, `db`, and `redis` are running
- the backend container sees the configured host mounts for:
  - full-ingestion scratch
  - ListenBrainz data
  - backups
  - node_exporter textfile metrics
- the ListenBrainz archive path is configured or passed explicitly
- no other full ingestion lease is active for `listenbrainz`

Relevant env vars are collocated in [`template.env`](/srv/juke-dev/template.env).

## Default Operating Mode

The default policy is `interactive`.

That means:

- extraction starts conservatively
- load/finalize budgets are bounded to preserve SSH responsiveness
- the controller will reduce throughput under sustained scratch, I/O, or memory pressure

Switch to `throughput` only when the host can tolerate higher NVMe pressure.

## Start A New Run

Use the bounded pipeline path:

```bash
docker compose exec backend python manage.py ingest_dataset_full \
  --provider listenbrainz \
  --execute-pipeline
```

If you need an explicit archive path:

```bash
docker compose exec backend python manage.py ingest_dataset_full \
  --provider listenbrainz \
  --archive-path /path/to/listenbrainz-full.tar \
  --execute-pipeline
```

## Inspect Status

Compact operator view:

```bash
docker compose exec backend python manage.py ingest_dataset_status \
  --provider listenbrainz
```

JSON view:

```bash
docker compose exec backend python manage.py ingest_dataset_status \
  --provider listenbrainz \
  --json
```

Read these fields first:

- `stage`
- `status`
- `finalize.phase`
- `finalize.drained_partitions`
- `finalize.hot_built_partitions`
- `cleanup.event_load_rows`
- `cleanup.session_load_rows`
- `cleanup.session_stage_rows`
- `cleanup.finalize_checkpoint_rows`
- `counters.scratch_actual_bytes`
- host pressure counters:
  - `host_device_util_milli_pct`
  - `host_iowait_milli_pct`
  - `host_available_memory_bytes`
  - `host_swap_used_bytes`

## Change Runtime Policy Or Budgets

Inspect the current control state:

```bash
docker compose exec backend python manage.py ingest_dataset_control \
  --provider listenbrainz
```

Switch to throughput mode:

```bash
docker compose exec backend python manage.py ingest_dataset_control \
  --provider listenbrainz \
  --policy throughput
```

Lower budgets explicitly:

```bash
docker compose exec backend python manage.py ingest_dataset_control \
  --provider listenbrainz \
  --partition-budget 4 \
  --load-budget 2 \
  --merge-budget 2
```

Raise the scratch soft cap if needed:

```bash
docker compose exec backend python manage.py ingest_dataset_control \
  --provider listenbrainz \
  --scratch-soft-cap-gb 500
```

## Resume An Interrupted Run

Resume the full pipeline:

```bash
docker compose exec backend python manage.py ingest_dataset_full \
  --provider listenbrainz \
  --resume \
  --execute-pipeline
```

Resume only finalize:

```bash
docker compose exec backend python manage.py ingest_dataset_full \
  --provider listenbrainz \
  --resume \
  --execute-merge-stage
```

Use `--force` only when you intentionally want to reset the current stage executor state. Avoid it for ordinary resume.

## Expected Storage Pressure

Observed on Neptune for the completed run:

- final cold table:
  - `mlcore_listenbrainz_event_ledger` about `638 GB`
- final hot table:
  - `mlcore_listenbrainz_session_track` about `469 GB`
- canonical identity table:
  - `mlcore_canonical_item` about `52 GB`

During active ingestion:

- scratch can rise into the hundreds of GB during extract/copy
- the controller uses a soft scratch cap and host-pressure signals to reduce throughput before the host becomes unusable
- finalize is the heaviest hot-storage phase

After a successful run:

- partition scratch should be removed
- runtime load/stage/checkpoint tables should be truncated back to minimal size

## Verify Cleanup After Success

Run:

```bash
docker compose exec backend python manage.py ingest_dataset_status \
  --provider listenbrainz \
  --json
```

Success cleanup looks like:

- `stage = "complete"`
- `status = "succeeded"`
- `cleanup.partition_root_exists = false`
- `cleanup.log_root_exists = false`
- `cleanup.spool_exists = false`
- `cleanup.event_load_rows = 0`
- `cleanup.session_load_rows = 0`
- `cleanup.session_stage_rows = 0`
- `cleanup.finalize_checkpoint_rows = 0`
- `cleanup.run_root_residue_bytes` is small

## Verify Training Readiness

Run the lightweight readiness check:

```bash
docker compose exec backend python manage.py verify_full_ingestion_dataset \
  --provider listenbrainz \
  --json
```

This command:

- loads the completed full-ingestion manifest
- samples eligible hot ListenBrainz sessions from `mlcore_listenbrainz_session_track`
- builds a small in-process PMI preview
- builds a small leave-one-out dataset preview

Healthy output should show:

- `ready = true`
- nonzero `sample_sessions_loaded`
- nonzero `sample_pairs`
- nonzero `sample_trials`

If the command reports that `mlcore_canonical_item` or `mlcore_listenbrainz_session_track` is missing, the backend container is not pointed at the database that holds the finished MLCore dataset. Fix the database configuration before attempting downstream training.

## Failure / Recovery Notes

- If the run fails during extract or copy, resume with `--resume --execute-pipeline`.
- If the run fails during finalize, prefer `--resume --execute-merge-stage`.
- If host responsiveness degrades, lower budgets first before stopping the run.
- If runtime tables drift out of shape after code changes, the load-table bootstrapper will rebuild them on the next run.

## Retained Dataset

The intended retained state after success is:

- `mlcore_listenbrainz_event_ledger`
- `mlcore_listenbrainz_session_track`
- `mlcore_canonical_item`

The runtime workspace should not retain data between runs:

- `mlcore_listenbrainz_event_load`
- `mlcore_listenbrainz_session_delta_load`
- `mlcore_listenbrainz_session_track_stage`
- `mlcore_listenbrainz_finalize_checkpoint`
