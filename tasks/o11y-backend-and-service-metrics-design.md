---
id: o11y-backend-and-service-metrics-design
title: Observability - backend and service metrics design
status: todo
priority: p2
owner: codex
area: platform
label: OBSERVABILITY
labels:
  - juke-task
  - o11y
  - backend
  - metrics
complexity: 4
updated_at: 2026-04-12
---

## Goal

Define a consistent metrics design for the Juke backend and adjacent services so operational dashboards and alerts can cover application health, queue throughput, ingestion jobs, and service-to-service dependencies without ad hoc metric naming.

## Scope

- Inventory the backend and service surfaces that need first-class metrics.
- Define naming conventions, label discipline, and cardinality constraints.
- Distinguish what should be emitted as:
  - Prometheus counters/gauges/histograms
  - node_exporter textfile metrics
  - structured logs only
- Specify baseline metrics for:
  - Django API request health
  - Celery worker and queue health
  - MLCore ingestion/training flows
  - recommender-engine request/latency/error behavior
  - Redis and Postgres dependency symptoms surfaced at the app layer
- Define dashboard and alert groupings that should exist once the metric set is implemented.

## Out Of Scope

- Building a full OTEL stack.
- Replacing the existing Neptune Prometheus + Grafana deployment.
- Deep application tracing.

## Acceptance Criteria

- A written metric taxonomy exists for Juke backend and accompanying services.
- Each metric family defines:
  - metric name
  - type
  - units
  - allowed labels
  - expected cardinality
  - operational purpose
- The design distinguishes batch-job metrics from request/response metrics.
- The design includes a first pass at dashboard groupings and alert candidates.

## Design Notes

- Prefer low-cardinality metrics suitable for long-running Prometheus retention.
- Keep partition- or user-level detail out of Prometheus unless it is strictly bounded.
- Use the node_exporter textfile collector for host-local batch and one-shot job state where that remains the simplest path.
- Keep manifest files and structured logs as the source of truth for high-cardinality forensic details.

## Suggested Outputs

- `docs/arch/...` design note for the metrics contract
- one or more Grafana dashboard JSON assets in `o11y/`
- implementation follow-up tasks by subsystem

## Initial Questions

- Which backend request paths need latency histograms vs simple counters?
- Which Celery queues need backlog, age, and failure-rate metrics?
- Which MLCore jobs need run-level vs partition-level visibility?
- Which service metrics belong in app code versus existing infrastructure exporters?
