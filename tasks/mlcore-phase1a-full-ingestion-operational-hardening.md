---
id: mlcore-phase1a-full-ingestion-operational-hardening
title: ML Core Phase 1a Follow-up - Full ingestion operational hardening
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
  - operations
complexity: 4
updated_at: 2026-04-22
---

## Goal

Turn the now-successful ListenBrainz full-ingestion path into a repeatable, supportable operational workflow on Neptune.

## Scope

- Harden the finalize executor so hot-build throughput keeps pace with drain without manual intervention.
- Improve end-of-run metrics and status reporting so the final index/swap tail is obvious to operators.
- Normalize cleanup/retention policy for:
  - manifest/control residue
  - checkpoint rows
  - runtime load/stage table lifecycle
- Produce an explicit runbook for:
  - start
  - resume
  - live throttle changes
  - post-run cleanup verification
- Validate downstream ML/training use of the finished canonical-item hot dataset.

## Out Of Scope

- New recommendation model architecture work.
- Non-ListenBrainz provider ingestion.
- Frontend or user-facing recommendation presentation changes.

## Acceptance Criteria

- A subsequent full ListenBrainz ingestion can be started and resumed without ad hoc operator intervention.
- Temporary load/stage tables are always empty after success and reclaimed to minimal on-disk size.
- Operator status surfaces clearly distinguish:
  - drain progress
  - hot-build progress
  - index/constraint tail
  - swap completion
- A short downstream ML verification demonstrates that the finished hot canonical-item dataset is usable for cooccurrence/training workflows.
- The Neptune runbook documents expected storage pressure, control commands, and recovery procedures.

## Handoff

- Input artifacts from the completed run:
  - final cold table `mlcore_listenbrainz_event_ledger`
  - final hot table `mlcore_listenbrainz_session_track`
  - canonical identity table `mlcore_canonical_item`
- Architecture background:
  - `docs/arch/MLCORE_LISTENBRAINZ_FULL_INGESTION_V3.md`
- Preceding completed task:
  - `tasks/mlcore-phase1a-listenbrainz-ingestion.md`
