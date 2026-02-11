---
id: mlcore-phase0-corpus-license-policy
title: ML Core Phase 0 - Corpus manifest and fail-closed license policy
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
complexity: 4
updated_at: 2026-02-11
---

## Goal

Implement strict corpus governance so production ML uses only license-compliant tracks from an auditable manifest.

## Scope

- Add `mlcore_corpus_manifest` table.
- Add policy enforcement service for `JUKE_ALLOWED_LICENSES` and fail-closed behavior.
- Block ingestion/training for unknown or non-permitted license rows.
- Add admin/inspection access for corpus manifest rows and policy decisions.
- Add model promotion guard: models trained with research-only rows cannot become active in production.

## Out Of Scope

- Ranking algorithm implementation.
- OpenL3 extraction worker logic.

## Acceptance Criteria

- Every embedding/training pipeline query is manifest-backed.
- Production mode skips non-compliant or unknown-license rows.
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
- Policy misconfiguration could silently starve model training.

## Handoff

- Completed:
- Next:
- Blockers:
