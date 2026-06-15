---
id: mlcore-musicbrainz-isrc-bridge-ingestion
title: MLCore MusicBrainz MBID to ISRC bridge ingestion
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
  - identity
complexity: 4
updated_at: 2026-06-15
---

## Goal

Build a compact, replay-safe bridge from MusicBrainz recording MBIDs to ISRCs using local dump data, and preserve any MusicBrainz external URL evidence useful for provider alias enrichment.

## Scope

- Load only the MusicBrainz tables needed to connect `recording.gid` to ISRC values.
- Keep raw/staging tables in cold storage.
- Materialize a compact bridge table, for example `mlcore_musicbrainz_recording_isrc`.
- Extract relevant MusicBrainz URL relationships for Spotify or other platform links when present.
- Add indexes for lookup by recording MBID and by ISRC.
- Record dump version, row counts, duplicate counts, and import timing.

## Out Of Scope

- Creating MLCore canonical aliases from ISRC rows.
- Spotify track lookup.

## Acceptance Criteria

- Import can run from local dump files without public API calls.
- Bridge rows are idempotent by `(recording_mbid, isrc, source_version)`.
- Import reports:
  - total MusicBrainz recordings scanned
  - total ISRC rows
  - unique recording MBIDs with at least one ISRC
  - duplicate ISRC rows
  - malformed/rejected ISRC rows
  - external URL relationship rows scanned and extracted
- Bridge table tablespace placement is explicit.
- Tests cover parsing, idempotency, malformed rows, and provenance.

## Execution Notes

- Prefer a compact hot-or-warm bridge only if resolver jobs need frequent access.
- Keep large raw staging data in cold storage.
- Risks:
  - Not every MusicBrainz recording has an ISRC.
  - Some recordings can have multiple ISRCs.
  - ISRC coverage is metadata-dependent and will not guarantee 100% MLCore canonical coverage.
  - MusicBrainz provider links may be release-level rather than recording-level and require careful confidence scoring.
- Design reference: `docs/arch/MLCORE_IDENTITY_GRAPH_HYDRATION_DESIGN.md`.

## Handoff

- Completed: cold bridge schema, one-pass streaming importer, replay-safe materialization, provenance counters, provider URL classification, operator command, and database-backed tests.
- Validation: 500 backend tests pass with 6 expected skips; focused MusicBrainz suite has 13 passing tests.
- Live execution: official release `20260613-002047` staged and verified; detached bridge import is running in `juke-musicbrainz-bridge`.
- Next: observe the live import through completion, record production row/storage counts, then hand its compact evidence to the separate canonical alias hydration task.
- Blockers: none.
