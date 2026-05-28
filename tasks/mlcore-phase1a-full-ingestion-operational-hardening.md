---
id: mlcore-phase1a-full-ingestion-operational-hardening
title: ML Core Phase 1a Follow-up - Full ingestion operational hardening
status: done
priority: p1
owner: codex
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - data-ingestion
  - operations
complexity: 4
updated_at: 2026-05-28
---

## Goal

Turn the now-successful ListenBrainz full-ingestion path into a repeatable, supportable operational workflow on Neptune.

## Scope

- Harden the finalize executor so hot-build throughput keeps pace with drain without manual intervention.
- Improve end-of-run metrics and status reporting so the final index/swap tail is obvious to operators.
- Normalize cleanup/retention policy for:
  - manifest/control residue
  - checkpoint rows
  - runtime load/stage table lifecycle
- Produce an explicit runbook for:
  - start
  - resume
  - live throttle changes
  - post-run cleanup verification
- Validate downstream ML/training use of the finished canonical-item hot dataset.

## Out Of Scope

- New recommendation model architecture work.
- Non-ListenBrainz provider ingestion.
- Frontend or user-facing recommendation presentation changes.

## Acceptance Criteria

- A subsequent full ListenBrainz ingestion can be started and resumed without ad hoc operator intervention.
- Temporary load/stage tables are always empty after success and reclaimed to minimal on-disk size.
- Operator status surfaces clearly distinguish:
  - drain progress
  - hot-build progress
  - index/constraint tail
  - swap completion
- A short downstream ML verification demonstrates that the finished hot canonical-item dataset is usable for cooccurrence/training workflows.
- The Neptune runbook documents expected storage pressure, control commands, and recovery procedures.

## Handoff

- Input artifacts from the completed run:
  - final cold table `mlcore_listenbrainz_event_ledger`
  - final hot table `mlcore_listenbrainz_session_track`
  - canonical identity table `mlcore_canonical_item`
- Architecture background:
  - `docs/arch/MLCORE_LISTENBRAINZ_FULL_INGESTION_V3.md`
- Operator runbook:
  - `docs/arch/MLCORE_LISTENBRAINZ_FULL_INGESTION_RUNBOOK.md`
- Preceding completed task:
  - `tasks/mlcore-phase1a-listenbrainz-ingestion.md`

## Completed Work

- Added explicit finalize subphase reporting and backlog visibility to:
  - `ingest_dataset_status`
  - Prometheus metrics emitted by the full-ingestion engine
- Normalized successful-run cleanup so the runtime ListenBrainz load/stage/checkpoint tables are truncated back to minimal size.
- Preserved tiny manifest/control residue while removing large partition/log scratch.
- Added `verify_full_ingestion_dataset` for lightweight downstream training-readiness checks against the finished canonical-item hot dataset.
- Wrote the Neptune runbook covering:
  - start
  - resume
  - runtime throttle changes
  - post-run cleanup verification
  - downstream readiness verification

## Post-Completion Operational Note - 2026-05-28

- Incremental remote sync is active on Neptune, not stale:
  - five `mlcore.tasks.sync_listenbrainz_remote` workers are currently importing ListenBrainz incrementals for `2026-04-23` through `2026-04-27`
  - the active `SourceIngestionRun` rows are making progress and updating `metadata.last_progress_at`
- The overlap happened because the daily beat task can start another remote sync while previous incremental imports are still running. Each new sync skips the already in-flight release, then begins the next missing release.
- Added a conservative remote-sync guard in `backend/mlcore/services/listenbrainz_source.py`: after expiring genuinely stale runs, a sync now returns `noop` while any ListenBrainz import is still `pending` or `running`.
- Cleared four queued duplicate `mlcore.tasks.sync_listenbrainz_remote` Redis messages from the `mlcore` queue so they do not start additional old-code syncs when a worker slot frees up.
- On user request, stopped the five active incremental sync tasks before the next full cooccurrence training run:
  - terminated the active Celery sync tasks/workers
  - confirmed `celery inspect active` is empty
  - confirmed Redis `mlcore` queue length is `0`
  - stopped the worker from consuming the `mlcore` queue with `celery control cancel_consumer mlcore`
  - marked the five interrupted `SourceIngestionRun` rows as `failed` with `metadata.stage=paused_for_cooccurrence_training`
  - preserved each run's `last_committed_checkpoint` for resume
- Paused incremental versions and checkpoint lines:
  - `listenbrainz-dump-2502-20260423-000004-incremental`: line `7,317,000`
  - `listenbrainz-dump-2503-20260424-000003-incremental`: line `6,842,500`
  - `listenbrainz-dump-2504-20260425-000004-incremental`: line `5,696,500`
  - `listenbrainz-dump-2505-20260426-000003-incremental`: line `5,771,500`
  - `listenbrainz-dump-2506-20260427-000003-incremental`: line `4,223,500`
- Resume expectation: after cooccurrence training, re-enable the worker's `mlcore` consumer with `celery control add_consumer mlcore`; the importer should find these failed runs by matching path/fingerprint and resume from their checkpoints.
