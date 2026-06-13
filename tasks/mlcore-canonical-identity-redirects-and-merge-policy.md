---
id: mlcore-canonical-identity-redirects-merge-policy
title: MLCore canonical identity redirects and merge policy
status: ready
priority: p1
owner: unassigned
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - identity
complexity: 4
updated_at: 2026-06-11
---

## Goal

Define and implement how MLCore safely converges separate MSID, MBID, Spotify, and catalog canonical items when enrichment proves they represent the same recording.

## Scope

- Add a canonical identity edge or redirect table.
- Represent high-confidence `same_recording` links between canonical items.
- Prefer canonical targets in this order:
  - `recording_mbid`
  - `spotify_track`
  - `recording_msid`
  - `catalog_track`
- Make serving resolution follow active redirects.
- Record source, source version, confidence, and evidence.
- Surface conflicts without automatic destructive merges.
- Design a later offline compaction/reassignment path for aliases and model artifacts.

## Out Of Scope

- Immediate destructive reassignment of all existing aliases.
- Rewriting historical training runs.

## Acceptance Criteria

- MSID->MBID mappings can resolve to the MBID-preferred canonical item without deleting the MSID canonical item.
- Conflicting mappings are represented and excluded from active serving resolution.
- Resolver endpoints and recommendation output code follow active redirects.
- Tests cover simple redirect, redirect chain, conflict, cycle prevention, and unchanged unresolved items.
- Dashboard metrics show redirect coverage and conflicts.

## Execution Notes

- This task is required because many MSID and MBID identities already exist as separate canonical item rows.
- Redirects allow gradual graph convergence while preserving historical artifact interpretability.

## Handoff

- Completed: task created from identity graph hydration design.
- Next: design model/migration and resolver changes.
- Blockers: none.
