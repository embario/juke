# Juke Independent ML Core — Architecture & Backend Migration Plan

**Version:** 1.1  
**Date:** 2026-02-11  
**Status:** Approved direction (decisions locked)  
**Scope:** Backend + recommender engine + data pipeline

---

## 1. Executive Summary

Juke will replace its Spotify-coupled ML internals with an independent recommendation core that is safe for long-term monetization.

Core principles:

- Keep `catalog` models as the holistic source of truth for Artist, Album, Track, Genre.
- Introduce global Juke identifiers (`juke_id`) and MBIDs on catalog resources.
- Treat Spotify and other streaming IDs as optional adapters, not canonical identity.
- Enforce strict license governance (`fail-closed`) for any audio used in production ML.
- Replace legacy hash-based recommendation internals fully (no backward-compatibility layer required).
- Serve a hybrid recommender with explainable score components in API responses.

Architecture stays the same at system level:

- Django = orchestration + API + jobs + policy enforcement
- FastAPI = scoring and retrieval engine
- PostgreSQL (+ pgvector) = data and vector retrieval
- Docker Compose = deploy/runtime

---

## 2. Decisions Locked

These decisions are approved and should be treated as implementation constraints.

1. **Licensing/Corpus policy:** production ML uses only production-safe datasets/licenses; no production benefit means dataset excluded.
2. **License enforcement:** fail-closed.
3. **Data model direction:** augment existing `catalog` models with Juke/MBID/external IDs; keep corpus metadata separate.
4. **Seed coverage:** all resource types (artist, album/release, track/recording, genre).
5. **Compatibility:** no legacy compatibility requirement; remove obsolete ML code.
6. **Latency target:** Option B (`P95 <= 150ms`) for content/hybrid retrieval path.
7. **Model promotion gate:** enforce offline metric thresholds before activation.
8. **Explainability:** include signal-level scores in API responses by default.
9. **Weight control:** DB-config only, no per-request override.
10. **Rollback:** switch active model to previous known-good row.
11. **Juke IDs:** use UUIDv7 for new `juke_id` fields.
12. **External IDs:** use per-resource adapter tables (not one polymorphic table).
13. **ANN index strategy:** start with `IVFFlat` to fit current memory constraints.
14. **Default response size:** `limit=10`.
15. **Phase-2 content model:** start with OpenL3.
16. **Embedding eligibility:** allow embedding with `juke_id` + licensed corpus link even when MBID is missing.
17. **Tag source policy:** blend both MusicBrainz tags and internal taxonomy.
18. **Promotion approver:** initial manual approver is the project owner.

---

## 3. Production Dataset and License Strategy

## 3.1 Monetization-first data posture

Juke should not rely on corpora that cannot be used in production monetized products.

### Recommended day-1 production-safe foundation

- MusicBrainz metadata graph (CC0)
- MetaBrainz/ListenBrainz open datasets where terms allow production use
- First-party derived features (computed by Juke from licensed/allowed assets)

### Excluded from production by default

- Datasets with non-commercial/research-only constraints
- Datasets with unclear redistribution/use terms

These may be used only in isolated research experiments if explicitly configured, but must not flow into production model artifacts.

Promotion rule:

- A model is production-eligible only if **all** training rows are production-compliant.
- Any model trained with `allowed_envs=research` rows is blocked from activation in production.

## 3.2 Fail-closed policy details

If any corpus row has:

- missing license metadata,
- unknown permission status,
- conflicting rights annotations,

then that row is not used in production embedding jobs or model training.

---

## 4. Target Backend Topology

## 4.1 Django app responsibilities

- `catalog` (existing): canonical resources + identity augmentation
- `recommender` (existing): recommendation API orchestration
- `mlcore` (new): corpus manifest, model registry, embeddings, co-occurrence, evaluation, health

## 4.2 FastAPI engine responsibilities

- `POST /engine/recommend/metadata`
- `POST /engine/recommend/cooccurrence`
- `POST /engine/recommend/content`
- `POST /engine/recommend` (hybrid, production)

## 4.3 Storage responsibilities

- `catalog_*`: canonical resources and identifiers
- `mlcore_*`: ML artifacts, corpus governance, scoring configs, health
- pgvector: ANN retrieval on track embeddings (initial index strategy: IVFFlat)

---

## 5. Data Model Plan (Catalog-Augmenting)

This plan **does not** introduce duplicate canonical artist/album/track entity tables.

## 5.1 Catalog model augmentation

Augment existing models in `backend/catalog/models.py`:

### `Artist`
- add `juke_id` UUIDv7 unique not null
- add `mbid` UUID nullable indexed

### `Album`
- add `juke_id` UUIDv7 unique not null
- add `mbid` UUID nullable indexed

### `Track`
- add `juke_id` UUIDv7 unique not null
- add `mbid` UUID nullable indexed

### `Genre`
- add `juke_id` UUIDv7 unique not null
- add optional canonical external genre IDs as needed

Canonical identity precedence:

1. `juke_id` (internal global identifier)
2. `mbid` (canonical external identity when available)
3. adapter IDs (`spotify_id`, others)

Embedding eligibility:

- A track can be embedded if it has a valid `juke_id` and a license-compliant corpus manifest entry.
- `mbid` is preferred but not required for embedding coverage.

## 5.2 External ID adapter tables (per resource class)

Add:

### `catalog_artist_external_id`
- `id` UUID PK
- `artist_juke_id` UUIDv7 FK to `Artist.juke_id`
- `source` text (`spotify`,`apple_music`,`youtube_music`,`musicbrainz`, ...)
- `external_id` text
- `created_at` timestamptz
- unique (`source`,`external_id`)

### `catalog_album_external_id`
- `id` UUID PK
- `album_juke_id` UUIDv7 FK to `Album.juke_id`
- `source` text
- `external_id` text
- `created_at` timestamptz
- unique (`source`,`external_id`)

### `catalog_track_external_id`
- `id` UUID PK
- `track_juke_id` UUIDv7 FK to `Track.juke_id`
- `source` text
- `external_id` text
- `created_at` timestamptz
- unique (`source`,`external_id`)

### `catalog_genre_external_id`
- `id` UUID PK
- `genre_juke_id` UUIDv7 FK to `Genre.juke_id`
- `source` text
- `external_id` text
- `created_at` timestamptz
- unique (`source`,`external_id`)

Requirements:

- no downstream service assumes any single provider ID exists
- `spotify_id` remains usable but non-canonical

## 5.3 Corpus manifest table (separate, as requested)

Add `mlcore_corpus_manifest`:

- `id` UUID PK
- `source` text
- `track_path` text
- `license` text
- `license_url` text nullable
- `allowed_envs` enum (`production`,`research`,`both`)
- `checksum` text
- `duration_ms` int nullable
- `track_juke_id` UUID nullable FK to `Track.juke_id`
- `mbid_candidate` UUID nullable
- `fingerprint` text nullable
- `ingested_at` timestamptz
- unique (`source`,`track_path`,`checksum`)

Hard rule: all files used by embedding/training jobs must appear in manifest.

## 5.4 Co-occurrence, model registry, embeddings, evaluation, health

Add:

### `mlcore_item_cooccurrence`
- `item_a_juke_id` UUID
- `item_b_juke_id` UUID
- `co_count` int
- `pmi_score` double precision
- unique (`item_a_juke_id`,`item_b_juke_id`)

### `mlcore_embedding_model`
- `id` UUID PK
- `name` text
- `source_model` text (`openl3`,`musicnn`,`custom`) — initial production baseline is OpenL3
- `embedding_dim` int
- `training_corpus_hash` text
- `version` text
- `active` boolean
- `is_known_good` boolean
- `created_at` timestamptz
- unique (`name`,`version`)

### `mlcore_track_embedding`
- `track_juke_id` UUID FK to `Track.juke_id`
- `model_id` UUID FK `mlcore_embedding_model`
- `vector` vector
- `pooled_from` int
- `created_at` timestamptz
- unique (`track_juke_id`,`model_id`)

### `mlcore_ranking_weight_config`
- `w_content` double precision
- `w_metadata` double precision
- `w_cooccurrence` double precision
- `lambda_mmr` double precision
- `active` boolean
- `created_at` timestamptz

### `mlcore_model_evaluation`
- `model_id` UUID
- `metric_name` text
- `metric_value` double precision
- `dataset_hash` text
- `created_at` timestamptz

### `mlcore_model_health_metrics`
- `metric_name` text
- `metric_value` double precision
- `model_id` UUID nullable
- `metadata` jsonb
- `created_at` timestamptz

---

## 6. Configuration Contract

Add settings in Django + FastAPI:

- `JUKE_ALLOWED_LICENSES=production|research|both`
- `JUKE_LICENSE_FAIL_CLOSED=1`
- `JUKE_RECOMMENDER_LATENCY_TARGET_P95_MS=150`
- `JUKE_RECOMMENDER_DEFAULT_LIMIT=10`
- `JUKE_VECTOR_INDEX_TYPE=ivfflat`
- `JUKE_ACTIVE_EMBEDDING_MODEL` (optional override)

Behavior:

- Production jobs must filter corpus rows to policy-compliant records only.
- If policy cannot be determined, skip the item (fail-closed).

---

## 7. API Contracts (Engine)

Default `limit` for all recommend endpoints is `10` unless explicitly overridden.

## 7.1 `POST /engine/recommend/metadata`

Input:

- `seed_item_ids` (Juke IDs)
- `exclude_ids`
- `limit` (default 10)

Scoring baseline:

- same artist: +1.0
- same release/album: +0.8
- shared genre/tag (from MusicBrainz tags + internal taxonomy): +0.5
- shared work relation: +0.4

## 7.2 `POST /engine/recommend/cooccurrence`

Input:

- `seed_item_ids`
- `exclude_ids`
- `limit` (default 10)

Scoring:

- aggregate PMI/co-occurrence scores.

## 7.3 `POST /engine/recommend/content`

Input:

- `seed_item_ids`
- `exclude_ids`
- `limit` (default 10)

Scoring:

- ANN search in pgvector using active `mlcore_embedding_model`.

Performance target:

- P95 <= 150ms.

## 7.4 `POST /engine/recommend` (hybrid production endpoint)

Input:

- `seed_item_ids`
- `exclude_ids`
- `limit` (default 10)

Weights:

- always loaded from active `mlcore_ranking_weight_config`
- no per-request weight overrides

Formula:

`final = w_content * content + w_metadata * metadata + w_cooccurrence * cooccurrence`

Diversification:

`MMR = lambda * relevance - (1 - lambda) * similarity_to_selected`

### Explainability output (required)

Each recommendation item must include:

- `content_score`
- `metadata_score`
- `cooccurrence_score`
- `final_score`
- `model_version`
- `weight_config_id`

---

## 8. Django API Orchestration Contract

`POST /api/v1/recommendations/` should move to canonical seed payloads:

- `seed_items` (artist/album/track/genre identifiers mapped to Juke IDs)
- `limit`
- optional `resource_types`

No backward compatibility requirement:

- remove legacy seed-shaping logic and old hash-oriented pathways.

---

## 9. Phased Implementation Checklist (Execution-Ready)

## Phase 0 — Identity, Licensing, Corpus Governance

Deliverables:

- augment catalog models with `juke_id` and `mbid`
- create per-resource external ID tables:
  - `catalog_artist_external_id`
  - `catalog_album_external_id`
  - `catalog_track_external_id`
  - `catalog_genre_external_id`
- create `mlcore_corpus_manifest`
- implement strict fail-closed corpus policy enforcement

Exit criteria:

- identity resolution works across Juke ID, MBID, and adapter IDs
- production ingestion excludes all non-compliant corpus rows

## Phase 1 — Baselines + Evaluation Harness

Deliverables:

- metadata and co-occurrence endpoints
- co-occurrence trainer jobs
- offline evaluation harness persisted in `mlcore_model_evaluation`

Promotion gate defaults:

- `nDCG@10` >= +5% relative vs active
- `Recall@10` >= +3% relative vs active
- cold-start regression <= 2%
- coverage >= 30%

Promotion ownership:

- Initial promotion approver is the project owner (manual approval step).

## Phase 2 — Content Embedding Pipeline

Deliverables:

- model registry + active model selection (initial model family: OpenL3)
- embedding worker (idempotent/resumable)
- pgvector ANN content retrieval (IVFFlat)

Exit criteria:

- P95 <= 150ms for target query profile
- model version switchable via DB row activation

## Phase 3 — Hybrid Ranking Layer

Deliverables:

- unified hybrid endpoint
- MMR diversification
- explainable score outputs per item

Exit criteria:

- hybrid outperforms each individual signal model
- better cold-start performance than co-occurrence-only

## Phase 4 — Production Hardening

Deliverables:

- nightly re-embedding for new/stale tracks
- health metrics ingestion and dashboard feed
- known-good model tracking and fast activation switching

Exit criteria:

- active model swap < 1 minute operationally
- continuous model health telemetry

---

## 10. Legacy Code Removal Plan

After hybrid path is live and validated, remove old ML internals:

- hash-token embedding code in `backend/recommender_engine/app/main.py`
- obsolete legacy serializer/view payload paths in `backend/recommender/*`
- obsolete tests that assert SHA-1 behavior
- obsolete ingestion tasks/services tied only to deprecated ML flow

This is a hard replacement, not a soft-compatibility migration.

---

## 11. Deployment Sequencing

1. Deploy schema changes (catalog augmentation + mlcore tables + pgvector).
2. Backfill IDs and external mappings.
3. Deploy baseline rankers + evaluation harness.
4. Deploy embedding worker and content endpoint.
5. Deploy hybrid endpoint and activate DB weight config.
6. Remove legacy ML code paths.

---

## 12. Rollback Strategy (Within New ML System)

Rollback means configuration/model rollback, not reverting to legacy ML.

Procedure:

1. Mark previous known-good model row as `active=true`.
2. Deactivate current model row.
3. Keep data in place (no deletion).

No engine redeploy required for model rollback.

---

## 13. Final State Definition

At completion, Juke ML is:

- independent from Spotify for core recommendation quality
- monetization-safe by strict license governance
- catalog-centric with unified Juke IDs and adapter mappings
- explainable, measurable, and operationally reversible
