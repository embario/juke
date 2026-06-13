---
id: mlcore-identity-graph-resource-cost-dashboard
title: MLCore identity graph resource cost and long-run progress dashboard
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
updated_at: 2026-06-11
---

## Goal

Expose the time, storage, and coverage cost of long-running MLCore identity graph enrichment work.

## Scope

- Track raw dump bytes, expanded staging bytes, active graph bytes, and table/index growth.
- Track coverage by source:
  - MSID->MBID redirect coverage
  - MBID->ISRC coverage
  - ISRC->Spotify coverage
  - platform alias coverage by provider
- Track job throughput and ETA:
  - dump download
  - dump extraction
  - alias materialization
  - Spotify hydration
- Track external resolution health:
  - request rate
  - `429` count
  - retry/backoff state
  - match/no-match/ambiguous rates
- Show both whole-catalog coverage and serving-candidate coverage.

## Out Of Scope

- Implementing the enrichment jobs themselves.

## Acceptance Criteria

- Grafana dashboard shows current identity graph storage cost by table and tablespace.
- Dashboard shows total graph coverage and prioritized serving coverage.
- Dashboard can answer whether Neptune is making useful progress even when full hydration is years away.
- Metrics include projected completion dates at current and configured throughput.

## Execution Notes

- Reuse node-exporter textfile metrics for long-running batch jobs.
- Reuse existing tablespace monitoring where possible.
- Serving-candidate coverage should be a first-class panel so whole-catalog incompleteness does not obscure practical readiness.

## Handoff

- Completed: task created from identity graph hydration design.
- Next: add queries/metrics after the first enrichment jobs land.
- Blockers: enrichment schema names need to settle.
