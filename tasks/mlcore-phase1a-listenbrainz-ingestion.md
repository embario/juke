---
id: mlcore-phase1a-listenbrainz-ingestion
title: ML Core Phase 1a - ListenBrainz dataset ingestion and interaction normalization
status: ready
priority: p1
owner: unassigned
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - data-ingestion
complexity: 5
updated_at: 2026-03-19
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

- Next: hook normalized output into `mlcore/services/cooccurrence.py` and evaluator/training split selectors.
- Blocker: none.

## Dependencies

- Prerequisite: `mlcore-phase0-corpus-license-policy` must be in place so all imported rows are policy-gated.
- Follows: foundational to `mlcore-phase1c-hybrid-training-data-corpus`.
