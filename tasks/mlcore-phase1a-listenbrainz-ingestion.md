---
id: mlcore-phase1a-listenbrainz-ingestion
title: ML Core Phase 1a - ListenBrainz dataset ingestion and interaction normalization
status: in_progress
priority: p1
owner: codex
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - data-ingestion
complexity: 5
updated_at: 2026-04-09
---

## Goal

Build a production-safe ingest pipeline for ListenBrainz full + incremental dumps and convert raw listen events into training-grade, canonicalized interaction rows.

## Scope

- Add scheduled full-import job for ListenBrainz `fullexport` snapshots.
- Add incremental replay job for ListenBrainz daily/near-daily increments.
- Add import progress/version metadata per run (`source_version`, raw path, checksum, row counts).
- Parse and persist event fields into a normalized ML event staging table.
- Handle re-import idempotency and duplicate suppression.
- Produce a canonicalized output table (MBID + sessionized context) for cooccurrence / LTR training.
- Add basic ingestion health checks and fail-fast behavior for malformed files.

## Out Of Scope

- Hybrid model architecture design.
- Ranking score calibration.
- UI recommendation presentation changes.

## Acceptance Criteria

- Full and incremental ingest runs are resumable and idempotent.
- Duplicate raw events are suppressed by stable event signature.
- Ingestion creates versioned source rows with deterministic `source_row_count` and checksums.
- Incremental job appends cleanly without corruption and preserves previously imported rows.
- At least one parser test covers a representative compressed dump slice.
- Ingested interaction table includes at minimum:
  - `source_user_id` (hashed/anonymized)
  - `track_identifier_candidates` (track MBID + fallback IDs)
  - `played_at`
  - `session_hint`
  - `source_id`, `source_version`

## Execution Notes

### Proposed components

- `backend/mlcore/ingestion/listenbrainz.py` (new): full/incremental fetch + parse + write.
- `backend/mlcore/models.py`: staging + run metadata models (if not already generic across other pipelines).
- `backend/mlcore/tasks.py`: Celery tasks:
  - `import_listenbrainz_full_task`
  - `replay_listenbrainz_incremental_task`
- `backend/settings/base.py`: ingest schedule/env settings.

### Suggested Django/MLCore paths

- `backend/mlcore/ingestion/__init__.py`
- `backend/mlcore/ingestion/listenbrainz.py`
- `backend/mlcore/services/listenbrainz_source.py`
- `backend/tests/unit/test_listenbrainz_ingest.py`

### Data model notes

- Keep raw source rows immutable and write canonicalized rows in separate normalized table.
- Never mix raw user IDs with production analytics IDs.
- Ensure raw filenames and manifest references remain for provenance replay.

## Risks

- Schema drift in official dumps.
- Large tarball size requires chunked streaming import.
- Duplicate user hashing approach can change over code revisions if salt changes.

## Handoff

- Completed:
  - Added `SourceIngestionRun`, `ListenBrainzRawListen`, and `NormalizedInteraction` models plus migration `backend/mlcore/migrations/0004_mlcore_listenbrainz_ingestion.py`.
  - Implemented file-based ListenBrainz import service at `backend/mlcore/ingestion/listenbrainz.py` with:
    - tar.gz / gz JSON-line parsing
    - deterministic file checksuming
    - stable event-signature dedupe
    - hashed source user IDs
    - session hints
    - canonical track resolution via MBID / Spotify fallback
    - fail-fast malformed-row handling with transactional rollback
  - Added Celery entrypoints `import_listenbrainz_full_task` and `replay_listenbrainz_incremental_task`, queue routing, and beat schedule/config hooks in `backend/settings/base.py`.
  - Added read-only admin visibility for source runs, raw listens, and normalized interactions.
  - Added blended behavioral source selection in MLCore basket builders so training/evaluation defaults now include both `listenbrainz` normalized interactions and internal `search_history` baskets.
  - Wired the new source selector through:
    - `backend/mlcore/services/cooccurrence.py`
    - `backend/mlcore/services/evaluation.py`
    - `backend/mlcore/management/commands/evaluate_recommenders.py`
  - Added operational training entrypoints for explicit source selection:
    - `backend/mlcore/management/commands/train_cooccurrence.py`
    - `backend/mlcore/tasks.py` now accepts `split`, `split_buckets`, and `sources`
  - Added unit coverage in `backend/tests/unit/test_listenbrainz_ingest.py`; verified with:
    - `docker compose exec backend python manage.py test tests.unit.test_listenbrainz_ingest tests.unit.test_license_policy tests.unit.test_mlcore_admin tests.unit.test_identity_resolver`
    - `docker compose exec backend python manage.py makemigrations --check --dry-run mlcore`
    - `docker compose exec backend python manage.py test tests.unit.test_cooccurrence_trainer tests.unit.test_evaluation`
    - `docker compose exec backend python manage.py test tests.unit.test_mlcore_pipeline tests.unit.test_mlcore_coverage_gaps`
- Remaining:
  - Run an end-to-end remote sync against the live FTP source in this environment and tune retention / operational limits after the first real backfill.
- Next:
  - Stage the latest upstream full dump `listenbrainz-dump-2461-20260315-000003-full` locally, then trigger `sync_listenbrainz_remote` (or the equivalent full import) and tune retention / operational limits after the first real backfill.
- Additional completed on 2026-03-23:
  - Fixed real full-dump compatibility in `backend/mlcore/ingestion/listenbrainz.py`:
    - `.listens` member discovery
    - streaming tar iteration for large `.tar.zst` archives
    - support for `timestamp` rows and MBIDs stored under `track_metadata.additional_info`
  - Added scheduled remote dump sync scaffolding:
    - new discovery/download/import service `backend/mlcore/services/listenbrainz_source.py`
    - new management command `backend/mlcore/management/commands/sync_listenbrainz_remote.py`
    - new Celery task `mlcore.tasks.sync_listenbrainz_remote`
    - beat schedule/env knobs for remote sync in `backend/settings/base.py` and `template.env`
    - compose mount change so backend/worker can stage downloaded dumps under `/srv/data/listenbrainz`
  - Added regression tests in:
    - `backend/tests/unit/test_listenbrainz_ingest.py`
    - `backend/tests/unit/test_listenbrainz_source_sync.py`
- Additional completed on 2026-03-28:
  - Normalized file-derived ListenBrainz `source_version` values so manual/file-based imports now strip archive suffixes and convert artifact filenames like `listenbrainz-listens-dump-*.tar.zst` into the same canonical release IDs used by remote sync (`listenbrainz-dump-*`).
  - Updated remote-sync artifact staging to reuse already-downloaded dumps stored directly under `MLCORE_LISTENBRAINZ_DOWNLOAD_DIR`, avoiding unnecessary re-downloads when older/manual artifacts are present in the legacy layout.
  - Changed the nightly remote-sync policy to prefer the existing local/imported full baseline and only fetch/apply newer incremental dumps after that baseline; the job now falls back to downloading a remote full baseline only when no usable local/imported full baseline exists.
  - Hardened source-version matching for existing ingestion runs so older rows that stored artifact filenames instead of canonical release IDs are still recognized as the same baseline/incremental releases by the scheduler.
  - If a local full-baseline import is already in flight, the nightly sync now returns `noop` instead of downloading a newer remote full in parallel.
  - Recreated the `backend` and `worker` containers so `/srv/data/listenbrainz` is now mounted read-write and the worker is subscribed to the `mlcore` queue.
  - Verified the ListenBrainz-focused backend suites still pass:
    - `docker compose exec backend python manage.py test tests.unit.test_listenbrainz_ingest tests.unit.test_listenbrainz_source_sync`
  - Checked the live upstream release index:
    - latest full dump as of 2026-03-28: `listenbrainz-dump-2461-20260315-000003-full`
    - latest incrementals observed: through `listenbrainz-dump-2474-20260328-000003-incremental`
  - Operational note:
    - the host currently only has the older full artifact `listenbrainz-listens-dump-2446-20260301-000003-full.tar.zst`, so a real remote sync today would need to download the newer `2461` full baseline before replaying later incrementals.
- Additional completed on 2026-03-29:
  - Completed the dataset-viability/legal pass for ListenBrainz against project docs plus MetaBrainz primary-source policy pages.
  - Determination: ListenBrainz full + incremental dumps can move from `research_only` to `production_approved` for Juke commercialization.
  - Basis:
    - MetaBrainz datasets page lists ListenBrainz dumps as `Commercial use: Allowed` and licensed under `Creative Commons Zero (CC0)`.
    - MetaBrainz GDPR statement says ListenBrainz listens are public, included in public dumps, and explicitly used to build recommendation engines.
  - Required operating constraints remain unchanged:
    - keep `source_user_id` hashed/pseudonymous,
    - do not ingest or train on user-facing profile fields,
    - preserve periodic full rebuilds because incrementals do not encode deletions.
  - Additional completed on 2026-04-09:
  - Switched the ListenBrainz ingest write path away from deprecated wide-row dual writes:
    - new hot training facts land in `ListenBrainzSessionTrack`
    - compact replay/dedupe facts land in `ListenBrainzEventLedger`
    - legacy `ListenBrainzRawListen` and `NormalizedInteraction` rows are no longer populated by the importer
  - Switched MLCore ListenBrainz basket loading for cooccurrence/evaluation to read `ListenBrainzSessionTrack` instead of `NormalizedInteraction`.
  - Added PostgreSQL tablespace split support for fresh juke-dev rebuilds:
    - fixed tablespace names:
      - `juke_mlcore_hot`
      - `juke_mlcore_cold`
    - admin-supplied host-path env vars:
      - `MLCORE_PG_HOT_TABLESPACE_HOST_PATH`
      - `MLCORE_PG_COLD_TABLESPACE_HOST_PATH`
    - fixed Postgres-internal locations:
      - `/var/lib/postgresql/tablespaces/juke_mlcore_hot`
      - `/var/lib/postgresql/tablespaces/juke_mlcore_cold`
    - migrations `backend/mlcore/migrations/0008_mlcore_tablespace_split.py` and `backend/mlcore/migrations/0009_reapply_mlcore_tablespace_split.py` create those tablespaces and move compact hot tables plus cold/deprecated ListenBrainz tables into place.
- Blocker: none.

## Dependencies

- Prerequisite: `mlcore-phase0-corpus-license-policy` must be in place so all imported rows are policy-gated.
- Follows: foundational to `mlcore-phase1c-hybrid-training-data-corpus`.
