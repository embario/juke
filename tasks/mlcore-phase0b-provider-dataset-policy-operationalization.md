---
id: mlcore-phase0b-provider-dataset-policy-operationalization
title: ML Core Phase 0b - Provider-specific dataset policy operationalization
status: ready
priority: p1
owner: unassigned
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - compliance
  - data-governance
complexity: 4
updated_at: 2026-03-29
---

## Goal

Translate the dataset licensing matrix into enforceable MLCore source modeling so
provider-specific rights constraints are encoded before new metadata and content
ingestion phases land.

## Why This Sits In Phase 0

This work should happen after generic corpus-policy enforcement exists, but
before provider-specific ingestion pipelines multiply the number of source
shapes. It has minimal hard dependencies and reduces rework across Phase 1b,
Phase 1c, and Phase 2 by settling source IDs, rights boundaries, and promotion
rules up front.

## Scope

- Convert the canonical matrix in `docs/arch/MLCORE_DATASET_VIABILITY_ASSESSMENT.md`
  into an implementation contract for MLCore source IDs.
- Define the provider/source partition plan for mixed-rights datasets, including:
  - `musicbrainz` vs `musicbrainz_supplemental`
  - `discogs_cc0` vs `discogs_restricted`
  - `fma_metadata` vs `fma_audio`
  - `jamendo` research-only unless separately cleared
  - `spotify_mpd` blocked
- Define the minimum provenance and policy metadata each provider ingest must
  write to `CorpusManifest`.
- Extend `SOURCE_CLASSIFICATION` and supporting tests/docs for source IDs that
  are approved now or intentionally blocked now.
- Add explicit promotion expectations for mixed-rights providers so downstream
  training/orchestration work cannot accidentally merge restricted rows into
  production artifacts.
- Update downstream MLCore tasks to depend on this source-partitioning contract
  where relevant.

## Initial Source ID Plan

These are the source IDs that should exist after the first implementation pass.

- `musicbrainz` — production-approved CC0 canonical/core subset.
- `listenbrainz` — production-approved behavioral source.
- `musicbrainz_supplemental` — non-CC0 MusicBrainz supplemental subset.
- `discogs_cc0` — production-approved Discogs metadata subset.
- `discogs_restricted` — blocked Discogs restricted/API-derived subset.
- `fma_metadata` — research-only metadata subset pending attribution path.
- `fma_audio` — research-only audio subset pending per-track rights handling.
- `jamendo` — research-only provider bucket unless a narrower approved split is
  later justified.
- `spotify_mpd` — blocked benchmark-only bucket.
- `juke_first_party` — production-approved internal behavioral/product data
  when a manifest-backed internal source path is introduced.

## Recommended Rollout Order

This is the minimum-dependency order that moves the broader MLCore roadmap
forward fastest.

### Step 1: Registry and tests

- Add the explicit source IDs above to `SOURCE_CLASSIFICATION`.
- Mark only these as `production_approved` in the first pass:
  - `musicbrainz`
  - `listenbrainz`
  - `discogs_cc0`
  - `juke_first_party` if implemented in code at the same time
- Mark these as `research_only` in the first pass:
  - `musicbrainz_supplemental`
  - `fma_metadata`
  - `fma_audio`
  - `jamendo`
- Mark these as `blocked` in the first pass:
  - `discogs_restricted`
  - `spotify_mpd`

### Step 2: Manifest contract

- Document the required `CorpusManifest` conventions per provider:
  - exact `source` string
  - expected `license`
  - expected `allowed_envs`
  - any required provenance notes in `license_url` or source-version metadata
- Make sure downstream ingests never overload one source ID for mixed-rights
  rows.

### Step 3: Downstream task alignment

- Update Phase 1b ingest design to write `musicbrainz` vs
  `musicbrainz_supplemental`, and `discogs_cc0` vs `discogs_restricted`.
- Update Phase 2 content/extraction design to write `fma_metadata` separately
  from `fma_audio`.
- Update Phase 1c / Phase 2 trainer expectations so production promotion uses
  the split source IDs rather than broad provider names.

## First Test Cases To Implement

These should be the first concrete tests added or updated in
`tests/unit/test_license_policy.py`.

- `classify_source('listenbrainz') == production_approved`
- `classify_source('discogs_cc0') == production_approved`
- `classify_source('discogs_restricted') == blocked`
- `classify_source('musicbrainz_supplemental') == research_only`
- `classify_source('fma_audio') == research_only`
- `classify_source('spotify_mpd') == blocked`
- production-mode `eligible_queryset()` includes:
  - `musicbrainz`
  - `listenbrainz`
  - `discogs_cc0`
- production-mode `eligible_queryset()` excludes:
  - `musicbrainz_supplemental`
  - `discogs_restricted`
  - `fma_metadata`
  - `fma_audio`
  - `jamendo`
  - `spotify_mpd`
- promotion guard blocks any training corpus containing:
  - `research_only` source IDs even if row `allowed_envs='production'`
  - blocked source IDs
  - any row whose `allowed_envs='research'`
- fail-closed behavior still blocks unknown sources.

## First Implementation Cut

The first PR for this task should stay narrow:

- update `SOURCE_CLASSIFICATION`
- update `test_license_policy.py`
- update `docs/arch/MLCORE_DATASET_VIABILITY_ASSESSMENT.md` if any source ID
  names need final normalization
- do not start provider ingestion code in the same change

That gives later ingestion phases a stable policy contract without coupling this
task to parser/loader work.

## Out Of Scope

- Building the actual provider ingestion pipelines.
- Negotiating commercial licenses with third-party providers.
- Replacing legal counsel review for ambiguous providers.

## Acceptance Criteria

- `docs/arch/MLCORE_DATASET_VIABILITY_ASSESSMENT.md` is treated as the canonical
  source-review matrix, and this task records how it maps into MLCore source IDs.
- Every mixed-rights provider in scope has an explicit source-partition plan
  rather than one coarse source label.
- `backend/mlcore/services/corpus.py` reflects the approved and blocked source
  IDs that are settled now.
- Tests cover provider/source partition behavior for production admission and
  promotion blocking.
- The first implementation cut is small enough to land before provider-specific
  ingest work starts.
- `mlcore-phase1b-metadata-enrichment-ingestion` and
  `mlcore-phase2-openl3-embeddings-and-content-retrieval` reference this task as
  a prerequisite for provider-specific policy semantics.

## Execution Notes

- Key files:
  - `/Users/embario/Documents/juke/docs/arch/MLCORE_DATASET_VIABILITY_ASSESSMENT.md`
  - `/Users/embario/Documents/juke/backend/mlcore/services/corpus.py`
  - `/Users/embario/Documents/juke/backend/tests/unit/test_license_policy.py`
  - `/Users/embario/Documents/juke/tasks/mlcore-phase1b-metadata-enrichment-ingestion.md`
  - `/Users/embario/Documents/juke/tasks/mlcore-phase2-openl3-embeddings-and-content-retrieval.md`
- Commands:
  - `docker compose exec backend python manage.py test tests.unit.test_license_policy`
- Risks:
  - Overly coarse source IDs will make production promotion unsafe later.
  - Overly fine source IDs can create operational sprawl if the provider split is
    not grounded in real ingestion boundaries.
  - Ambiguous providers such as Jamendo may still require counsel/product review
    before any production admission decision is encoded.

## Handoff

- Completed:
- Next:
  - First PR should implement the registry expansion and targeted policy tests
    only, with no ingest/parser changes.
- Next:
- Blockers:
