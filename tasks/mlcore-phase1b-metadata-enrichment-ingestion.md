---
id: mlcore-phase1b-metadata-enrichment-ingestion
title: ML Core Phase 1b - Canonical metadata and external dump ingestion for hybrid features
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
complexity: 4
updated_at: 2026-03-19
---

## Goal

Ingest MusicBrainz canonical dumps, MusicBrainz PostgreSQL/JSON metadata, and Discogs monthly dumps into a canonical item/feature layer usable by both content and non-content rankers.

## Scope

- Add ingest jobs for:
  - MusicBrainz canonical dump
  - MusicBrainz metadata dump (core relational metadata)
  - Discogs monthly XML dumps (styles/labels/artist/linkage)
- Build canonical track/item mapping tables and crosswalks:
  - recording/artist/release canonical IDs
  - Spotify/MBID/other external ID adapters (via existing identity model paths)
- Backfill metadata feature tables used by ranking candidate generation and explainability:
  - artist/label/genre/style/era vectors
  - relationship-derived overlap signals
- Record source provenance per imported feature row.

## Out Of Scope

- OpenL3/audio extraction model training.
- Full recommendation serving endpoint changes.

## Acceptance Criteria

- Every ingested metadata row has source tags (`source`, `source_version`, `source_row_id`).
- Canonical IDs resolve to stable `juke_id` where possible with explicit `unresolved` bucket metrics.
- Metadata feature builders can run without external API calls using batch dumps.
- Re-import is replay-safe (idempotent or deterministic overwrite by stable keys).
- Ingestion fails closed when dump schema is incompatible or row-level license rules are violated.

## Execution Notes

### Proposed components

- `backend/mlcore/ingestion/musicbrainz.py` (new): canonical + metadata dump parser loaders.
- `backend/mlcore/ingestion/discogs.py` (new): XML monthly release/artist/style ingestion.
- `backend/mlcore/services/metadata_features.py` (new): transform normalized metadata into ML features.
- `backend/mlcore/tasks.py`:
  - `import_musicbrainz_canonical_task`
  - `import_musicbrainz_metadata_task`
  - `import_discogs_task`
- `backend/mlcore/admin.py`: optional status/admin surfaces for ingestion runs.

### Policy integration

- Reuse `LicensePolicy` in `backend/mlcore/services/corpus.py`.
- Source classification additions must be added to `SOURCE_CLASSIFICATION` during review milestones.

### Suggested test targets

- `tests/unit/test_dataset_ingestion_metadata.py`
- `tests/unit/test_identity_resolution_integration.py`

## Risks

- Metadata dumps are large and may require staged imports.
- Discogs XML entity matching is noisy without high-quality match keys.
- Non-aligned naming conventions can create false merges without confidence thresholds.

## Handoff

- Next: provide this feature layer as input to ranking feature builder and hybrid training sampler.
- Blocker: none.

## Dependencies

- Prerequisite: `mlcore-phase0-catalog-identity-adapters` for external ID tables and canonical resolution.
- Can run in parallel with `mlcore-phase1a-listenbrainz-ingestion` if storage is separated.
- Prerequisite to: `mlcore-phase1c-hybrid-training-data-corpus`.
