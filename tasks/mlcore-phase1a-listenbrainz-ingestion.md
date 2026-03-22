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
updated_at: 2026-03-22
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
  - Decide whether ListenBrainz should remain `research_only` or move to `production_approved` after the dataset-viability/legal pass.
  - Add production deployment wiring for configured dump paths/source versions.
- Next:
  - Decide whether Phase 1a is now complete enough to move to Phase 1b, or if we also want environment/docs polish around real dump operations first.
- Blocker: none.

## Dependencies

- Prerequisite: `mlcore-phase0-corpus-license-policy` must be in place so all imported rows are policy-gated.
- Follows: foundational to `mlcore-phase1c-hybrid-training-data-corpus`.
