---
id: mlcore-phase0-corpus-license-policy
title: ML Core Phase 0 - Corpus manifest and fail-closed license policy
status: review
priority: p1
owner: codex
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - compliance
complexity: 4
updated_at: 2026-03-05
---

## Goal

Implement strict corpus governance so production ML uses only license-compliant tracks from an auditable manifest, with MusicBrainz as the initial primary production training source.

## Scope

- Add `mlcore_corpus_manifest` table.
- Set initial production corpus source policy to MusicBrainz-only (`source=musicbrainz`) until additional sources pass review.
- Add policy enforcement service for `JUKE_ALLOWED_LICENSES` and fail-closed behavior.
- Block ingestion/training for unknown or non-permitted license rows.
- Classify corpus sources as `production_approved`, `research_only`, or `blocked` for explicit policy decisions.
- Add admin/inspection access for corpus manifest rows and policy decisions.
- Add model promotion guard: models trained with research-only rows cannot become active in production.

## Out Of Scope

- Ranking algorithm implementation.
- OpenL3 extraction worker logic.

## Acceptance Criteria

- Every embedding/training pipeline query is manifest-backed.
- Production mode skips non-compliant, unknown-license, and non-MusicBrainz rows by default.
- Promotion guard rejects models whose training corpus includes non-`production_approved` source rows.
- Policy decisions are test-covered and logged.
- Promotion guard rejects research-contaminated model rows.

## Execution Notes

- Key files:
- `/Users/embario/Documents/juke/backend/mlcore/models.py` (new)
- `/Users/embario/Documents/juke/backend/mlcore/services/corpus.py` (new)
- `/Users/embario/Documents/juke/backend/settings/base.py`
- Commands:
- `docker compose exec backend python manage.py makemigrations mlcore`
- `docker compose exec backend python manage.py migrate`
- `docker compose exec backend python manage.py test`
- Risks:
- Ambiguous license metadata across datasets can reduce usable corpus.
- MusicBrainz-only phase may reduce coverage until additional sources are approved.
- Policy misconfiguration could silently starve model training.

## Handoff

- Completed:
  - New `mlcore` app scaffolded and registered in `INSTALLED_APPS`.
  - `CorpusManifest` model (`mlcore/models.py`) with `mlcore_corpus_manifest` table: per-file provenance rows keyed on `(source, track_path, checksum)`. FK to `catalog.Track.juke_id` (nullable, `SET_NULL`) so manifest rows survive catalog deletion for audit. Indexed on `source` + `allowed_envs`. Migration `mlcore/migrations/0001_initial.py`.
  - `LicensePolicy` service (`mlcore/services/corpus.py`):
    - `classify_source()` — `SOURCE_CLASSIFICATION` registry, currently MusicBrainz-only as `production_approved`; unknown sources → `blocked` under fail-closed.
    - `evaluate(row)` — per-row `PolicyDecision(allowed, reason, classification)`. Fail-closed on missing license/allowed_envs.
    - `eligible_queryset()` — pipeline entry point; filters by mode (`production`/`research`/`both`).
    - `is_model_promotable(qs)` — deployment-time guard; rejects + WARNING-logs any model trained on non-production_approved or research-only rows.
  - Settings: `JUKE_ALLOWED_LICENSES` (default `production`), `JUKE_LICENSE_FAIL_CLOSED` (default `True`) in `settings/base.py` + `template.env`.
  - Admin (`mlcore/admin.py`): `CorpusManifestAdmin` surfaces per-row `policy_status` / `policy_reason` columns.
  - Tests: `tests/unit/test_corpus_manifest.py` (8), `tests/unit/test_license_policy.py` (22), `tests/unit/test_mlcore_admin.py` (5). Full suite: 214 tests pass. `ruff check .` clean (added `per-file-ignores` for generated migrations E501).
- Next:
  - Phase 1 embedding/training jobs must call `LicensePolicy().eligible_queryset()` as their sole corpus input path.
  - Populate `SOURCE_CLASSIFICATION` as new datasets pass review (additive change, no migration).
- Blockers:
  - None.
