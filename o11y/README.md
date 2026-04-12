# Observability Assets

This folder keeps repo-owned observability artifacts for Juke services.

Current contents:

- `mlcore-full-ingestion-dashboard.json`
  A Grafana dashboard for the MLCore full-ingestion engine. It visualizes the
  Prometheus textfile metrics emitted by `ingest_dataset_full` through Neptune's
  existing `node_exporter` textfile collector.

What the dashboard covers:

- active run state
- merged row count
- merged partition count
- elapsed wall-clock time
- row progress across parse, stage, and merge
- partition state distribution
- quality counters for deduplicated, unresolved, and malformed rows
- run metadata labels from `mlcore_full_ingestion_info`

Operational note:

- The live Neptune Grafana instance auto-loads dashboards from
  `/srv/monitoring/grafana/dashboards`.
- This repo folder is the versioned source copy.
- To deploy an updated dashboard, copy the JSON from this folder into the live
  Grafana dashboard directory or automate that step in future infrastructure
  work.
