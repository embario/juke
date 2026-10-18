---
id: mlcore-identity-reference-safeguards
title: Honor identity quarantines and validate ISRC hydration references
status: review
priority: p1
owner: codex
area: platform
label: BACKEND/ML
complexity: 4
updated_at: 2026-10-18
---

## Goal

Prevent held identity references from being reused or reactivated, and require recording metadata validation before accepting an ISRC-derived Spotify alias. Document the October investigation's mistakes and lessons.

## Scope

- Shared hold policy covering existing conflict/retired aliases and explicit quarantine annotations.
- Exclude held ISRC evidence from raw-fact bridge/clustering consumers; veto affected groups rather than silently dropping contradictory members.
- Protect hydration claims, retries, alias writes and benchmark reference selection.
- Retain source-versioned MusicBrainz title, artist credit and duration for validation; missing or inconsistent metadata fails closed.
- Regression tests using small isolated PostgreSQL fixtures; retrospective and safe rollout/backfill instructions.

## Out of scope

- Deployment, activating aliases/redirects, relaxing the 95% gate, restarting bulk services, provider API requests, rebuilding the completed ListenBrainz extraction pipeline, deleting source evidence.

## Acceptance criteria

- Held identifiers cannot produce aliases/redirects through the reviewed ingestion/cluster/hydration paths, including resumed writes and mixed-member clusters.
- Hydration cannot reactivate a same-owner held alias; source/reference name, artist and version disagreements or absent reference metadata are held with a reason.
- Unicode, joined credits and explicit master-year differences are covered by tests; benchmark excludes held references without treating them as successes.
- Source metadata retains provenance; metadata-only backfill is distinct from evidence replay.
- Focused PostgreSQL tests pass; reports distinguish implemented safeguards from deployment and independently validated precision.

## Execution notes

- ASYNC, owner explicitly requested safeguards and a retrospective. Isolated branch/worktree; preserve existing user changes and operational reports.
- Test against a dedicated Docker database on Neptune; never the live database. No provider network calls in tests.
- Existing eight-pair quarantine is operationally active; all bulk identity/hydration jobs stay paused.

## Handoff

Implemented and validated on `codex/identity-reference-safeguards`.

- Shared alias/queue hold policy protects raw ISRC bridges, Spotify groups, legacy and direct redirect writers, alias materialization, hydration/reconciliation, benchmark references and annotated-active serving aliases. Held members veto groups; new holds invalidate staged writes under the shared write lock.
- Source-versioned recording metadata includes archive checksum, title, complete artist credit and duration. Migration 0035 and metadata-only backfill command added; future bridge imports retain metadata. Missing source metadata holds hydration before API spending. Wrong title/credit/version/available duration or ISRC disagreements produce durable holds. No same-owner reactivation of held aliases/redirects.
- Comparison reports identify reference agreement, publish held/full denominators, and retain held cases outside the conservative gate numerator. The 95% threshold is unchanged. New B5/B6/B7 algorithm versions require rebuilt workspaces/checkpoints.
- Validation: 902-test complete backend suite passed (10 existing optional skips), followed by 143 focused tests against the final source, all passed. Ruff, `makemigrations --check --dry-run`, and diff whitespace checks passed. Tests ran in a private PostgreSQL 18/Redis Docker network on Neptune, with mocked providers and no live database mounts. New serving SQL also executes against a real small PostgreSQL fixture without optional FastAPI dependencies.
- Documents: `docs/ops/identity-reference-safeguards.md` (reviewed rollout/backfill/audit procedure) and `docs/ops/identity-resolution-retrospective-20261018.md` (specific mistakes, outcomes, limits and process changes). Validation artifacts: `/Users/embario/.local/state/juke-identity-reports/20261017/safeguards/`.
- Not deployed: no live migration, metadata backfill, service restart, API request, alias/redirect activation, graph promotion, or source deletion. Existing eight-pair quarantine remains active; bulk jobs stay paused. Next controlled step is code review followed by a separately authorized rollout/capacity review, metadata backfill and bounded audit before any promotion.

Historical context: Original investigation and remediation artifacts are under `/Users/embario/.local/state/juke-identity-reports/20261017/` and mirrored on Neptune. Source ISRC facts are immutable; the existing alias annotations must be honored by bulk paths, not just serving.
