---
id: mlcore-identity-resolution-coverage-observability
title: MLCore identity resolution coverage and observability
status: ready
priority: p1
owner: unassigned
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - observability
  - identity
complexity: 3
updated_at: 2026-06-09
---

## Goal

Make canonical identity coverage visible enough to decide whether MLCore can reliably serve Spotify-ID recommendations.

## Scope

- Add coverage metrics for canonical identity resolution stages:
  - canonical item source/type counts
  - MBID alias coverage
  - ISRC alias coverage
  - Spotify alias coverage
  - unresolved recommendation candidate rate
- Add dashboard panels for MusicBrainz ingestion, ISRC alias materialization, and Spotify output resolution.
- Add completion/progress metrics for each long-running job.
- Add coverage reports suitable for release gates.

## Out Of Scope

- Implementing the ingestion/resolution jobs themselves.

## Acceptance Criteria

- Grafana dashboard shows current identity coverage by canonical item type and alias source.
- Long-running MusicBrainz/ISRC/Spotify jobs expose active/progress/throughput/ETA/error counters.
- Reports can answer whether serving candidates are Spotify-resolvable before an API cutover.
- Coverage deltas are recorded per source version.

## Execution Notes

- Reuse existing node-exporter textfile metrics pattern for long-running materialization jobs.
- Add database summary queries for periodic coverage snapshots.
- Risks:
  - Whole-corpus coverage can look poor while top-candidate coverage is good; dashboards should show both.

## Handoff

- Completed: task created.
- Next: wire metrics as each job lands.
- Blockers: none.
