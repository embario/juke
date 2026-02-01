# Juke Music Recommendation Engine — Architecture Document

**Version:** 1.2
**Date:** 2026-01-31
**Status:** Phase 1 COMPLETE — Phase 2 ready to start
**Owner:** Recommender team

---

## 1. Purpose & Scope

This document defines the multi-phased plan to evolve Juke's recommendation system from its current prototype (SHA-1 hash-based token vectors with cosine similarity) into a production-grade, content-similarity recommendation engine backed by real audio-feature embeddings. The engine must answer the core question downstream apps will ask:

> *Given a seed of music resources (genres, artists, albums, tracks) and optionally a user's MusicProfile, return a ranked list of similar resources the user has not already seen.*

The design preserves the existing two-tier architecture (Django orchestrator + standalone FastAPI engine) and extends it in place rather than replacing it.

---

## 2. Current State Analysis

### 2.1 What exists today

| Layer | Location | Role |
|---|---|---|
| Django API | `recommender/views.py` — single `POST /api/v1/recommendations/` | Validates input, normalises seed lists via `taste.mixed_payload()`, proxies to engine, re-serialises response |
| Engine | `recommender_engine/app/main.py` — FastAPI, two endpoints | `POST /embed` generates a vector; `POST /recommend` scores all stored embeddings against a user vector |
| Embedding store | `recommender/models.py` — `ArtistEmbedding`, `AlbumEmbedding`, `TrackEmbedding` (OneToOne to catalog) | Persists vectors as `JSONField` alongside `model_version`, `quality_score`, `metadata` |
| Sync tasks | `recommender/tasks.py` — three `@shared_task` functions | One per resource type; each calls `POST /embed` on the engine and upserts the returned vector |
| Catalog | `catalog/models.py` — `Genre`, `Artist`, `Album`, `Track` | Core music entities, populated via Spotify search (live or stub) |
| User profile | `juke_auth/models.py` — `MusicProfile` | Stores `favorite_genres`, `favorite_artists`, `favorite_albums`, `favorite_tracks` as JSON arrays of name strings |

### 2.2 What the current engine actually does

The embedding model is deterministic and non-semantic. For any resource, the engine:

1. Extracts all string attribute values (name, spotify_id, artist names).
2. Runs each string through SHA-1, takes the first 32 bytes, interprets them as `uint8`, and accumulates into a 32-dimensional vector.
3. L2-normalises the result.

At recommendation time the same process is applied to the concatenation of all seed names to produce a "user vector", then every stored embedding is scored via cosine similarity against it.

**Critical limitation:** because both the seed vector and the candidate vectors are produced by the same deterministic hash function over name strings, two resources whose names share few characters will always score low regardless of how musically related they actually are. The engine has no concept of genre, audio features, or collaborative signal. It is, in effect, a string-similarity engine dressed as a recommendation system.

### 2.3 What needs to change

The hash-based approach must be replaced with embeddings that encode *musical* similarity. Specifically:

- Embeddings should incorporate **audio features** (tempo, key, energy, valence, danceability, etc.) that Spotify exposes per-track, plus **genre lineage** for artists.
- The training/ingestion pipeline must be an **asynchronous Celery task** that pulls audio features from Spotify in bulk, persists them as a training corpus, and then computes embeddings from that corpus.
- The engine's similarity scoring must remain cosine-based (it is well-suited to normalised embeddings) but operate on these richer vectors.
- The API contract must be extended to accept **Juke URIs** (`juke:artist:<spotify_id>`, `juke:album:<spotify_id>`, `juke:track:<spotify_id>`) as seed identifiers alongside plain name strings, so downstream apps can reference specific indexed resources unambiguously.
- A **CLI proof-of-concept** must exist to exercise the engine end-to-end outside of the HTTP stack.

---

## 3. Phased Plan

### Phase 1 — Training Data Collection ✓ COMPLETE

All acceptance criteria met.  116 tests passing.

**What was built:**

*Audio-feature ingestion (the original Phase 1 spec):*

- `recommender/models.py` — `TrackAudioFeatures` model (12 audio-feature fields, OneToOne to Track, `created_at`/`modified_at`).
- `recommender/migrations/0002_track_audio_features.py` — migration.
- `catalog/spotify_stub.py` — `audio_features()` stub returning deterministic per-track payloads via SHA-256.
- `recommender/services/audio_ingest.py` — crawl service: DFS over artists (alphabetical by name, spotify_id) → albums (alphabetical) → tracks (by track_number).  Batches at 50.  Skips tracks that already have a `TrackAudioFeatures` row (free resume).  Per-batch and per-track error handling; batch failures log enriched track names and continue.  Lazy Spotipy singleton.
- `recommender/tasks.py` — `ingest_training_data` Celery task shell (bind, autoretry, backoff, max_retries=3).  Includes an empty-catalog guard: if `Track.objects.count() == 0` it logs a warning pointing to `crawl_catalog` and returns immediately without retrying.
- `settings/base.py` — route `recommender.tasks.ingest_training_data` → `recommender` queue.
- `tests/unit/test_audio_ingest.py` — 7 tests covering full ingestion, field-range validation, DFS ordering, skip/resume, idempotency, batch-fetch failure continuation, and missing-track-in-response handling.

*Catalog hydration (prerequisite surfaced during implementation — the catalog had no background population path):*

- `catalog/spotify_stub.py` — `artist_albums()` and `album_tracks()` stubs returning deterministic paginated responses.
- `catalog/services/catalog_crawl.py` — crawl service: searches Spotify by each of the 10 genre seeds, deduplicates artists across seeds, then for each artist persists artist → albums → tracks via the existing serializers (`SpotifyArtistSerializer`, `SpotifyAlbumSerializer`, `SpotifyTrackSerializer`).  Key behaviours:
  - Album subtree skip: an album is skipped entirely (no track fetch, no re-save) when it already exists *and* has tracks.  Albums created by the on-demand HTTP path (which persist the album but not its tracks) are re-crawled.
  - Per-track `IntegrityError` catch: Spotify occasionally returns duplicate `track_number` values on an album (live versions, reissues).  These are logged as failed tracks and do not abort the album or artist.
  - Artist name consistency: the crawl rewrites album and track payloads' nested artist/album references with the canonical data already persisted, preventing unique-constraint collisions from name mismatches between Spotify's minimal stubs and the rows we created.
- `catalog/tasks.py` — `crawl_catalog_task` Celery task shell + route on `catalog` queue.
- `catalog/management/commands/crawl_catalog.py` — operator-invoked management command.
- `tests/unit/test_catalog_crawl.py` — 10 tests covering full crawl counts, DB population, artist↔album and album↔track linkage, idempotency (second run skips all album subtrees), partial-resume (pre-existing artist's albums skipped, rest created), album-without-tracks not skipped, per-artist fetch failure continuation, genre-search failure continuation, and duplicate-track-number isolation.

**Operator sequence (current state):**

```bash
python manage.py crawl_catalog          # 1. Populate Artist / Album / Track
# then enqueue or call ingest_training_data to populate TrackAudioFeatures
```

**Data model (as built):**

```
TrackAudioFeatures
├── track            → OneToOneField(Track)
├── energy           → FloatField        # 0.0–1.0
├── valence          → FloatField        # 0.0–1.0
├── tempo            → FloatField        # BPM
├── key              → IntegerField      # 0–11
├── mode             → CharField(5)      # 'major' | 'minor'
├── danceability     → FloatField
├── acousticness     → FloatField
├── instrumentalness → FloatField
├── liveness         → FloatField
├── speechiness      → FloatField
├── loudness         → FloatField        # dB, typically -60 to 0
├── time_signature   → IntegerField      # beats per measure
├── created_at       → auto
└── modified_at      → auto
```

---

### Phase 2 — Embedding Model (replace hash vectors)

**Goal:** Replace `_hash_tokens` in the FastAPI engine with an embedding function that projects the audio-feature corpus into a meaningful vector space. Artists and albums are embedded by aggregating their constituent track vectors.

**Embedding strategy:**

| Resource | Vector construction |
|---|---|
| Track | Direct projection of the 12 audio-feature dimensions into the target embedding dimension via a learnable linear layer (or, for the PoC, a fixed PCA-like projection matrix trained offline on the corpus). |
| Album | Mean of all constituent track embeddings (weighted by track duration). |
| Artist | Mean of all album embeddings for that artist. |

For the initial PoC the projection matrix is computed once via PCA on the `TrackAudioFeatures` corpus and stored as a static NumPy array (`model/projection.npy`) baked into the engine container image. This avoids a runtime training dependency while still producing semantically meaningful vectors.

Retraining is triggered manually via a management command (see Phase 4). The command recomputes the PCA matrix from the current corpus, writes it to `model/projection.npy`, and re-syncs all stored embeddings against the new projection. This gives operators explicit control over when the model changes, and the deterministic crawl order of Phase 1 means the corpus state is always reproducible.

**Engine changes:**

- New endpoint or internal function: given a `spotify_id` and resource type, look up the pre-computed embedding from the DB (same tables as today: `ArtistEmbedding`, `AlbumEmbedding`, `TrackEmbedding`).
- `POST /embed` is updated: when `resource_type` is `track`, it reads the corresponding `TrackAudioFeatures` row, applies the projection, and returns the vector. For `album` and `artist` it aggregates child embeddings as described above. The SHA-1 fallback remains for `text` type seeds that cannot be resolved to a catalog entity.
- The existing `_rank_candidates` and cosine-similarity logic is unchanged — only the vector content changes.

**Acceptance criteria for Phase 2:**
- Engine produces vectors from audio features, not from name hashes.
- Artist and album embeddings are correctly aggregated from children.
- Cosine similarity scores between musically similar resources are meaningfully higher than between dissimilar ones (validated manually against a small known corpus).

---

### Phase 3 — Juke URI Support & Profile-Based Seeding

**Goal:** Allow the recommendation API to accept seeds by Juke URI in addition to plain name strings, and allow seeding directly from a `MusicProfile` UUID.

**Juke URI format:**

```
juke:<resource_type>:<spotify_id>
```

Examples:
- `juke:artist:06HL4z0CvFAxyc27GXpf94`
- `juke:album:6i6folBtxKV9YJFir6QmV3`
- `juke:track:11dFrPrpdmdiFcJkjqyrUv`

**API contract changes (Django layer):**

The existing `RecommendationRequestSerializer` gains an optional field:

```
seeds: List[str]     # Juke URIs — resolved to embeddings directly
profiles: List[str]  # MusicProfile UUIDs — expanded to their favorite_* lists
```

The `seeds` field is resolved in the Django view layer: each URI is parsed, the corresponding catalog entity looked up, and its pre-computed embedding fetched. These resolved embeddings are sent to the engine as a `seed_vectors` list alongside any remaining name-string seeds. The engine computes a single user vector by combining all provided seed vectors (resolved + hash-based fallback for unresolved names). The relative weight between resolved and name-based seeds is controlled by a `seed_weight` parameter on the request (float, default `1.0`; resolved vectors are always weighted at `1.0`, name-based seeds are weighted at `seed_weight`). A client that wants resolved seeds to dominate sets `seed_weight` below 1.0; a client that wants equal treatment leaves the default.

The `profiles` field triggers a lookup of one or more `MusicProfile` rows. Each profile's `favorite_*` JSON arrays are flattened into the existing name-based seed lists.

**Exclusion semantics:** Seeds are excluded from results by `spotify_id` only. When a Juke URI is resolved, its `spotify_id` is added to the exclusion set that is forwarded to the engine. The engine's candidate-scoring loop drops any row whose `spotify_id` matches an entry in that set. Name-match exclusion is removed.

**Acceptance criteria for Phase 3:**
- `juke:` URIs are parsed and resolved to embeddings end-to-end.
- Invalid or unresolved URIs return a clear 400 error with the offending URI.
- `profiles` field correctly expands a MusicProfile into seed names.
- The engine handles a mix of resolved seed vectors and unresolved name strings in a single request.
- `seed_weight` correctly adjusts the influence of name-based seeds relative to resolved vectors.
- Exclusion is performed by `spotify_id`; seed resources do not appear in results.

---

### Phase 4 — CLI Proof of Concept

**Goal:** A standalone command-line tool that exercises the full recommendation pipeline without requiring a running Django server, suitable for development, debugging, and demo purposes.

**Design:**

Two management commands under `recommender/management/commands/`:

**`recommend.py`** — exercises the recommendation pipeline:

1. Accepts arguments:
   - `--seeds` — one or more Juke URIs or plain names.
   - `--profiles` — one or more `MusicProfile` UUIDs.
   - `--resource-types` — which output types to include (default: all three).
   - `--limit` — max results per type (default: 10).
   - `--seed-weight` — float controlling name-seed influence (default: 1.0).
2. Resolves seeds and profiles using the same logic as Phase 3 (reusing the service layer, not duplicating it).
3. Calls the engine's `/recommend` endpoint (or, if `--offline` is passed and the engine is not running, falls back to an in-process scoring path using the same NumPy logic).
4. Pretty-prints the ranked results as a table: name, resource type, likeness score, spotify_id.

**`retrain.py`** — recomputes the embedding model:

1. Reads all `TrackAudioFeatures` rows from the database.
2. Checks corpus viability before proceeding:
   - **Size check:** if fewer than 500 tracks have audio features, the command aborts with a warning. 500 is the minimum threshold because the 12×12 covariance matrix needs sufficient samples to stabilise, and the corpus needs enough stylistic breadth to separate genres meaningfully.
   - **Diversity check:** counts the number of distinct genres present across the artists that own the ingested tracks. If genre diversity is low relative to corpus size (fewer than ~10 distinct genres for a 500-track corpus), the command logs a warning but does *not* abort — low diversity is an advisory, not a blocker, since the operator may be intentionally training on a narrow slice.
3. Runs PCA on the audio-feature matrix to produce a new projection matrix.
4. Writes the matrix to `model/projection.npy` (path configurable via env).
5. Re-syncs all `TrackEmbedding`, `AlbumEmbedding`, and `ArtistEmbedding` rows against the new projection by invoking the existing sync tasks.
6. Logs corpus size, genre diversity count, explained-variance ratio of the PCA components, and how many embeddings were updated.

**Example invocations:**

```bash
# Recommend similar artists and tracks to two known artists
python manage.py recommend \
  --seeds juke:artist:06HL4z0CvFAxyc27GXpf94 juke:artist:1Cn0YMA3FoVTxqmuFxoEOT \
  --resource-types artists tracks \
  --limit 5

# Retrain the projection matrix from the current corpus
python manage.py retrain
```

**Acceptance criteria for Phase 4:**
- `recommend` runs without error against a seeded database.
- Output includes ranked results with likeness scores.
- `--offline` mode produces results without a running engine container.
- `--seed-weight` visibly changes result ranking.
- `retrain` aborts with a clear message if corpus has fewer than 500 tracks.
- `retrain` warns (but proceeds) if genre diversity is low.
- `retrain` recomputes the projection, re-syncs embeddings, and logs summary stats including genre diversity count and explained-variance ratio.
- Help text (`--help`) describes all arguments on both commands.

---

## 4. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                          CLIENT LAYER                                    │
│  Mobile / Web  ──►  POST /api/v1/recommendations/                       │
│                     { seeds: [...], profiles: [...], limit, types }      │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     DJANGO ORCHESTRATOR                                  │
│                                                                         │
│  RecommendationView                                                     │
│   1. Parse & validate (serializer)                                      │
│   2. Resolve `profiles` UUIDs → MusicProfile → seed name lists          │
│   3. Resolve `seeds` Juke URIs → look up pre-computed embeddings        │
│   4. Forward { seed_vectors, name_seeds, limit, resource_types }        │
│      to engine via recommender.services.client                          │
│   5. Normalise + return response                                        │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │  HTTP POST /recommend
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                     FASTAPI RECOMMENDER ENGINE                           │
│                                                                         │
│  POST /recommend                                                        │
│   1. Compute user vector:                                               │
│      • Average pre-resolved seed_vectors (weight 1.0)                   │
│      • Hash-embed any remaining name_seeds (weight = seed_weight)       │
│      • Combine via weighted average                                     │
│   2. For each requested resource_type:                                  │
│      • Fetch all stored embeddings from Postgres                        │
│      • Score each via cosine similarity                                 │
│      • Exclude by spotify_id (ID-only, no name matching)                │
│      • Sort descending, take top N                                      │
│   3. Return ranked lists                                                │
│                                                                         │
│  POST /embed                                                            │
│   • track  → read TrackAudioFeatures, apply projection matrix          │
│   • album  → aggregate child track embeddings                           │
│   • artist → aggregate child album embeddings                           │
│   • text   → SHA-1 fallback (legacy)                                    │
└────────────────────────────────┬────────────────────────────────────────┘
                                 │  direct SQL (psycopg pool)
                                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         POSTGRESQL                                      │
│                                                                         │
│  catalog_artist / catalog_album / catalog_track     (source of truth)   │
│  recommender_artistembedding / albumembedding / trackembedding          │
│  recommender_trackaudiofeatures                     (NEW — Phase 1)     │
│  juke_auth_musicprofile                             (user prefs)        │
└─────────────────────────────────────────────────────────────────────────┘
                                 ▲
                                 │  Celery workers
┌─────────────────────────────────────────────────────────────────────────┐
│                     ASYNC TASK LAYER                                     │
│                                                                         │
│  ingest_training_data          (Phase 1) — DFS crawl, audio features    │
│  sync_artist_embedding         (existing) — calls /embed, upserts      │
│  sync_album_embedding          (existing)                               │
│  sync_track_embedding          (existing)                               │
│                                                                         │
│  manage.py retrain             (Phase 4) — PCA recompute + re-sync     │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 5. Data Flow — Recommendation Request (Phase 3+)

```
User submits:
  seeds:       ["juke:artist:ABC", "juke:track:XYZ"]
  profiles:    ["<uuid>"]
  seed_weight: 0.5                          # name-seeds count at half influence
  limit:       10

Django view:
  ├─ Resolve profile <uuid> → MusicProfile.favorite_artists = ["Radiohead"]
  ├─ Resolve juke:artist:ABC → ArtistEmbedding.vector = [0.12, 0.45, ...]
  │                          → spotify_id "ABC" added to exclude set
  ├─ Resolve juke:track:XYZ  → TrackEmbedding.vector  = [0.33, 0.21, ...]
  │                          → spotify_id "XYZ" added to exclude set
  └─ Forward to engine:
       seed_vectors:  [[0.12, 0.45, ...], [0.33, 0.21, ...]]   # weight 1.0
       name_seeds:    ["Radiohead"]                              # weight 0.5
       exclude_ids:   ["ABC", "XYZ"]
       resource_types: ["artists", "albums", "tracks"]
       limit: 10

Engine:
  ├─ user_vector = weighted_avg(seed_vectors @ 1.0, hash("Radiohead") @ 0.5)
  ├─ Fetch all ArtistEmbedding rows
  │    → drop any where spotify_id in {"ABC", "XYZ"}
  │    → score remaining → top 10
  ├─ Fetch all AlbumEmbedding rows  → (same exclude + score) → top 10
  └─ Fetch all TrackEmbedding rows  → (same exclude + score) → top 10

Response:
  { artists: [{name, likeness, extra}, ...],
    albums:  [...],
    tracks:  [...],
    model_version, generated_at }
```

---

## 6. Key Design Decisions & Rationale

| Decision | Rationale |
|---|---|
| **Preserve the two-tier architecture** | The Django/FastAPI split already exists and works. Collapsing them would create a large migration with no clear benefit at this scale. |
| **PCA projection for PoC, not a neural net** | A learned neural embedding would require a training loop, GPU infra, and significant data. PCA on 12 audio-feature dimensions is sufficient to separate musical genres and is trivially retrained. It can be swapped for a richer model later without changing the API contract. |
| **Audio features as the training signal** | Spotify's audio-features endpoint is the richest structured signal available without requiring user listening history. It captures the sonic character of a track directly. Genre tags are complementary (good for artists) but too coarse on their own for track-level similarity. |
| **Aggregate child embeddings for albums/artists** | This is the simplest composable approach: an artist's vector is the centroid of their discography. It naturally handles artists with diverse catalogs and degrades gracefully when only partial data is available. |
| **Juke URIs over bare spotify_ids** | Namespacing prevents ambiguity (a Spotify ID alone does not tell you whether it is an artist, album, or track). The `juke:` prefix also decouples the external identifier from the internal DB PK, allowing future data-source changes. |
| **SHA-1 fallback retained** | Name-based seeds remain useful for profiles populated during onboarding (which store genre and artist *names*, not IDs). The fallback ensures backward compatibility with existing MusicProfile data without requiring a migration. |
| **Management commands for CLI PoC** | Django management commands have access to the ORM, settings, and Celery infrastructure out of the box. An `--offline` flag avoids a hard dependency on the engine container during development. |
| **VECTOR_DIM stays at 32** | PCA on 12 audio-feature dimensions saturates well below 32. Keeping 32 leaves headroom to incorporate genre-derived or collaborative features later without a schema change. |
| **Manual retraining via `manage.py retrain`** | Automated retraining on corpus-size thresholds introduces a hidden dependency between data ingestion and model state. An explicit management command gives operators full control over when the model changes and pairs naturally with the deterministic crawl order that makes the corpus state reproducible. |
| **`seed_weight` as a tunable request parameter** | Different downstream contexts (e.g. discovery vs. "more like this") have legitimately different intuitions about how much weight a loose name-based seed should carry relative to an explicitly resolved URI. A fixed ratio baked into the engine would require code changes to tune; a per-request float keeps the engine generic. |
| **DFS crawl order for `ingest_training_data`** | Alphabetical-by-artist with depth-first album→track traversal creates a deterministic, progress-trackable ordering. Because each artist is fully completed before the next begins, the operator can observe exactly how far the crawl has progressed at any time. Combined with idempotent upserts, this ordering provides natural stop/resume semantics without a separate cursor table. |
| **ID-only exclusion** | The project is early enough that existing MusicProfile data (which stores names, not IDs) does not need to be preserved. ID-based exclusion via `spotify_id` is exact and unambiguous, eliminating edge cases around name normalisation, duplicates, and partial matches. |

---

## 7. Dependency Map

| Phase | Depends on | Produces |
|---|---|---|
| 1 — Training data ✓ | Catalog populated | `crawl_catalog` task + mgmt cmd, `TrackAudioFeatures` table, `ingest_training_data` task + empty-catalog guard |
| 2 — Embedding model | Phase 1 corpus | Updated `/embed` logic, projection matrix, re-synced embeddings |
| 3 — URI + profile seeding | Phase 2 embeddings stored | Extended API contract, resolver logic |
| 4 — CLI PoC | Phase 3 resolver + engine | Management commands (`recommend`, `retrain`) |

---

## 8. Resolved Decisions Log

All questions raised during initial review have been resolved. Rationale for each is captured in the decisions table in §6.

| # | Question | Decision |
|---|---|---|
| 1 | Embedding dimension | Keep `VECTOR_DIM` at 32. Extend later if genre or collaborative features are added. |
| 2 | Retraining cadence | Manual only. `manage.py retrain` recomputes PCA and re-syncs all embeddings on demand. |
| 3 | Seed weighting | Tunable per-request via `seed_weight` float (default 1.0). Resolved vectors always weighted at 1.0; name-based seeds weighted at `seed_weight`. |
| 4 | Crawl scope | DFS over existing catalog: artists in alphabetical order, each artist fully completed (albums → tracks) before moving to the next. No related-artist discovery. |
| 5 | Exclusion semantics | ID-only. Seeds are excluded by `spotify_id` match. Name-match exclusion is removed. |

---

## 9. Success Criteria (overall)

- A validated `TrackAudioFeatures` corpus covering the full catalog.
- Embeddings that produce meaningfully higher cosine scores for musically similar resources than for dissimilar ones (spot-checked against a known test set).
- The recommendation API accepts seeds by Juke URI, by MusicProfile UUID, or by plain name — and correctly combines them.
- A CLI command that demonstrates end-to-end recommendation without a browser.
- All new code passes existing test conventions (`docker compose exec backend python manage.py test`).
- No breaking changes to the existing `POST /api/v1/recommendations/` contract for clients that still send plain name lists.

---

## 10. Phase 2 Entry Checklist

**Prerequisite — DONE.** `recommender/management/commands/ingest_audio_features.py` was added following the same thin pattern as `catalog/management/commands/crawl_catalog.py`.  All 116 tests pass.

The full operator sequence is now available and is the input to Phase 2:

```bash
python manage.py crawl_catalog              # catalog hydration (Phase 1)
python manage.py ingest_audio_features      # corpus population  (Phase 1)
python manage.py retrain                    # model recompute    (Phase 2 / Phase 4)
```

**Key files to read before starting Phase 2:**

| File | Why |
|---|---|
| `recommender_engine/app/main.py` | Contains the current SHA-1 `_hash_tokens` and `/embed` + `/recommend` endpoints that Phase 2 replaces/extends |
| `recommender/tasks.py` | Contains the existing `sync_*_embedding` tasks that Phase 2's retrain will re-invoke |
| `recommender/models.py` | `TrackAudioFeatures` (Phase 1 corpus) + the three embedding models that store the vectors |
| `catalog/services/catalog_crawl.py` | Understanding of what the catalog looks like after hydration |
| `recommender/services/audio_ingest.py` | Understanding of what the corpus looks like after ingestion |
