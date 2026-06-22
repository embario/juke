---
id: mlcore-canonical-identity-redirects-merge-policy
title: MLCore canonical identity redirects and merge policy
status: review
priority: p1
owner: codex
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - identity
complexity: 4
updated_at: 2026-06-22
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

- Completed: hot canonical redirect model, non-destructive MBID preference policy, source/version/evidence provenance, conflict exclusion, resolver traversal, and cycle/depth protection.
- Completed: cooccurrence serving expands preferred MBID seeds back to legacy MSID model IDs and maps recommended MSID neighbors forward to preferred MBIDs.
- Completed: unit/database tests cover direct and chained redirects, unchanged unresolved items, contradictory evidence, cycles, hot/cold placement, and existing-model serving compatibility.
- Completed: initial production MSID-to-MBID redirect materialization produced 7,790,712 active redirects against the pre-existing canonical corpus.
- Completed: expanded missing MSID canonical rows for 7,691,107 additional clean mappings and rematerialized redirects to the full 15,481,819 clean mapping set.
- Completed: added auditable conflict-resolution table and strict `shard-dominance-v1` resolver; production pass promoted 40,198 conflict MSIDs into active redirects and left ambiguous conflicts excluded.
- Next: add redirect coverage/conflict panels through `mlcore-identity-resolution-coverage-observability`; evaluate whether a second policy can safely resolve additional ambiguous conflicts.
- Blockers: none.
