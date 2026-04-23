# Observability Assets

This folder keeps repo-owned observability artifacts for Juke services.

Current contents:

- `mlcore-full-ingestion-dashboard.json`
  A Grafana dashboard for the MLCore full-ingestion engine. It visualizes the
  Prometheus textfile metrics emitted by `ingest_dataset_full` through Neptune's
  existing `node_exporter` textfile collector.

The current ListenBrainz engine shape behind that dashboard is:

- one archive reader that spools monthly members to NVMe scratch
- bounded extractor processes that parse and compact rows into hash-chunk files
- lean cold/hot load tables fed by `COPY`
- set-based finalization that builds replacement hot/cold tables and swaps them
  into place atomically under the provider lease

What the dashboard covers:

- active run state
- merged row count
- merged partition count
- elapsed wall-clock time
- load progress across parse, compact event load, session-delta load, chunk production, and finalize
- partition state distribution
- quality counters for deduplicated, unresolved, and malformed rows
- run metadata labels from `mlcore_full_ingestion_info`
- lease-backed run selection via `provider` + active `run_id`

Operational note:

- The live Neptune Grafana instance auto-loads dashboards from
  `/srv/monitoring/grafana/dashboards`.
- This repo folder is the versioned source copy.
- To deploy an updated dashboard, copy the JSON from this folder into the live
  Grafana dashboard directory or automate that step in future infrastructure
  work.
