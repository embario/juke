# MLCore Dataset Viability Assessment

Date: March 29, 2026
Owner: platform / MLCore
Status: authoritative dataset licensing matrix for MLCore source review

## Purpose

This document is the canonical licensing matrix for datasets that can supplement
Juke MLCore. It records the current commercial-use determination, the MLCore
policy tier each source should map to, and the constraints that must remain in
place for production use.

This matrix is intentionally stricter than "can we technically download it?".
A source is only `production_approved` when we have a defensible basis to use
it in a monetized Juke product and the intended ML use fits within the source's
published terms.

## Decision Summary

| Dataset | Primary ML use in Juke | Commercial posture for Juke | MLCore source tier | Notes |
|---|---|---|---|---|
| Juke first-party behavioral data | ranking, eval, personalization | Allowed | `production_approved` | first-party product data |
| ListenBrainz full + incremental dumps | cooccurrence, behavioral ranking, hybrid training labels | Allowed | `production_approved` | keep privacy controls and pseudonymous IDs |
| MusicBrainz canonical data | identity normalization, MBID mapping | Allowed | `production_approved` | CC0 |
| MusicBrainz PostgreSQL core metadata | metadata ranker features, graph enrichment | Allowed for CC0 core only | `production_approved` for core subset | supplementary non-CC0 tables must stay out of prod |
| Discogs CC0 catalog metadata | genre/style/label enrichment | Allowed for CC0 subset | `production_approved` for CC0 subset | exclude restricted API/user/marketplace/image data |
| FMA metadata | content pretraining metadata, evaluation labels | Allowed with attribution obligations | `research_only` by default | split from audio before considering production |
| FMA audio | content embeddings / pretraining | Mixed and per-track | `research_only` | per-track rights review required |
| Jamendo catalog/API data | supplemental metadata, playlists, reviews | Conditional / unclear for broad commercial ML use | `research_only` | commercial rights may be required depending on use |
| Spotify MPD | offline benchmark only | Not allowed for production-commercial ML | `blocked` | challenge terms prohibit commercial use |

## Recommendation Workflow Mapping

This section answers a different question than licensing: what recommendation
workflows each dataset actually unlocks in MLCore.

| Dataset | Unlocks directly | Best use in Juke | What it supplements | What it does not provide well |
|---|---|---|---|---|
| Juke first-party behavioral data | user-personalized ranking, baskets, repeat-listen affinity, explicit in-product feedback loops | production personalization, online refresh, user-history recommendations | ListenBrainz and metadata/content features | cold-start for brand-new users and sparse catalog items |
| ListenBrainz full + incremental dumps | large-scale cooccurrence, user-item implicit signals, session-ish transitions, recency trends | collaborative candidate generation, seed-based item-to-item recs, warm-start rankers, hybrid labels | first-party data coverage and training volume | audio/content similarity and rich item semantics by itself |
| MusicBrainz canonical data | durable item identity graph | canonical seed resolution, de-duplication, cross-source joins | every behavioral/content source | user behavior, content similarity |
| MusicBrainz PostgreSQL core metadata | entity relationships, tags, artist/release context | metadata retrieval, explainable reranking, cold-start enrichment, artist/label/genre neighborhood recs | ListenBrainz, Discogs, first-party behavior | high-signal collaborative ranking on its own |
| Discogs CC0 catalog metadata | style/genre/label/era neighborhoods | style-aware related items, hard-negative pools, long-tail enrichment, explainability facets | MusicBrainz metadata and hybrid reranking | user behavior and audio similarity |
| FMA metadata | genre/tag supervision labels | content-model supervision, metadata-aware cold-start eval, genre-conditioned retrieval | FMA audio and OpenL3 pipelines | collaborative signals and production-safe behavior modeling |
| FMA audio | acoustic similarity signal | content embeddings, audio-nearest-neighbor retrieval, "sounds like" recs, cold-start track similarity | metadata rankers and hybrid models | user intent and collaborative popularity trends |
| Jamendo catalog/API data | small-scale playlist/review/community signals | prototyping playlist/radio heuristics, explicit-signal experiments, research-only enrichment | metadata enrichment and lightweight collaborative experiments | production-grade commercial foundation or high-scale behavior |
| Spotify MPD | playlist continuation benchmark structure | offline benchmark for playlist-next and set-completion models | model evaluation only | production training, identity fidelity, commercial deployment |

### What These Datasets Mean For Juke Recommendation Modes

#### 1. Current phase: cooccurrence from seeds and listening baskets

Already unlocked by:

- Juke first-party behavioral data
- ListenBrainz

What improves this mode:

- MusicBrainz canonical data makes seeds and candidates resolve to stable IDs.
- MusicBrainz + Discogs metadata help clean up false negatives and add better
  backoff when cooccurrence coverage is sparse.

#### 2. Warm-start collaborative recommendations

Primary datasets:

- ListenBrainz
- Juke first-party behavioral data

User-facing workflows enabled:

- "Because you listened to X"
- "Users who played X also played Y"
- recs from seed tracks/artists/albums
- personalized home/feed retrieval for users with history

#### 3. Session-aware and recency-aware recommendation

Primary datasets:

- ListenBrainz incrementals
- Juke first-party behavioral data

User-facing workflows enabled:

- next-up style recommendations
- trend-aware refreshes
- recent-listen continuation
- time-windowed popularity and replay-aware ranking

#### 4. Cold-start and sparse-item recommendation

Primary datasets:

- MusicBrainz core metadata
- Discogs metadata
- FMA metadata
- FMA audio

User-facing workflows enabled:

- recommendations for tracks with few or no listens
- related-by-genre / related-by-style / related-by-label suggestions
- "sounds similar" retrieval using content embeddings
- better seed expansion when collaborative data is thin

#### 5. Hybrid ranking and explainability

Primary datasets:

- ListenBrainz / first-party behavior for collaborative features
- MusicBrainz / Discogs for metadata features
- FMA-derived content models for acoustic similarity

User-facing workflows enabled:

- one ranker that blends behavior, metadata, and content
- explanation strings such as:
  - similar listeners liked this
  - same artist/label/style neighborhood
  - acoustically similar to your seed

#### 6. Offline benchmarking and model selection

Primary datasets:

- Spotify MPD
- FMA
- ListenBrainz historical slices

User-facing workflows enabled indirectly:

- safer model iteration before production promotion
- benchmark splits for playlist continuation, recall, nDCG, and cold-start
- ablation testing of metadata vs collaborative vs content features

## Matrix

### 1. Juke first-party behavioral data

- Proposed source id: `juke_first_party`
- MLCore tier: `production_approved`
- Why:
  - This is Juke's own product telemetry and behavioral data, subject to our
    own product terms and privacy program rather than third-party corpus terms.
- Allowed uses:
  - recommendation training
  - offline evaluation
  - ranking features
- Recommendation workflows unlocked:
  - personalized candidate generation from real Juke user history
  - repeat-affinity modeling
  - online refresh and post-launch feedback loops
- Required constraints:
  - keep product/privacy-policy alignment
  - maintain internal access controls for user-level data

### 2. ListenBrainz full + incremental dumps

- Proposed source id: `listenbrainz`
- MLCore tier: `production_approved`
- Commercial determination:
  - Allowed for Juke's commercial ML work.
- Why:
  - MetaBrainz datasets page lists ListenBrainz dumps as commercial-use
    allowed under CC0.
  - MetaBrainz's GDPR statement says ListenBrainz listens are public, included
    in public dumps, and explicitly used to build recommendation engines.
- Allowed uses:
  - cooccurrence training
  - behavioral rankers
  - hybrid training labels
  - offline evaluation
- Recommendation workflows unlocked:
  - item-to-item cooccurrence recommendations from seed tracks/albums/artists
  - warm-start collaborative filtering
  - session/time-aware ranking features
  - broader candidate generation than first-party data alone can provide early
- Required constraints:
  - hash or otherwise pseudonymize source user identifiers
  - do not carry user-facing profile fields into production ML artifacts
  - preserve full-refresh capability because incrementals do not encode deletions
  - commercial support of MetaBrainz is strongly urged, but that is a moral
    request rather than a stated license condition
- Primary sources:
  - https://metabrainz.org/datasets/postgres-dumps
  - https://metabrainz.org/gdpr
  - https://creativecommons.org/public-domain/cc0/

### 3. MusicBrainz canonical data

- Proposed source id: `musicbrainz`
- MLCore tier: `production_approved`
- Commercial determination:
  - Allowed for commercial use.
- Why:
  - Canonical MusicBrainz data is documented as CC0.
  - MetaBrainz states commercial users should financially support the project,
    but presents that as a moral request, not a license restriction.
- Allowed uses:
  - canonical ID mapping
  - MBID normalization
  - item identity joins
- Recommendation workflows unlocked:
  - reliable seed resolution across providers
  - de-duplicated candidate graphs
  - stable lineage for hybrid feature joins
- Required constraints:
  - treat canonical mappings as versioned, not permanently stable
- Primary sources:
  - https://musicbrainz.org/doc/Canonical_MusicBrainz_data
  - https://metabrainz.org/datasets/postgres-dumps
  - https://creativecommons.org/public-domain/cc0/

### 4. MusicBrainz PostgreSQL metadata

- Proposed source ids:
  - `musicbrainz` for CC0 core rows
  - `musicbrainz_supplemental` for any non-CC0 supplementary rows
- MLCore tier:
  - core subset: `production_approved`
  - supplemental non-CC0 subset: `research_only` or `blocked`
- Commercial determination:
  - Core metadata is commercially usable.
  - Supplementary non-commercial/share-alike data is not production-safe for
    Juke monetization.
- Why:
  - MetaBrainz datasets page distinguishes CC0 core data from supplementary
    CC BY-NC-SA data.
- Allowed uses:
  - metadata ranker features
  - relationship graph features
  - crosswalk generation
- Recommendation workflows unlocked:
  - related artist / release / track neighborhoods
  - explainable reranking features
  - cold-start backoff when behavior is sparse
- Required constraints:
  - physically or logically split CC0 core from supplementary tables
  - do not let supplementary rows enter production model artifacts
- Primary sources:
  - https://metabrainz.org/datasets/postgres-dumps
  - https://musicbrainz.org/doc/MusicBrainz_Database/Download

### 5. Discogs catalog metadata

- Proposed source ids:
  - `discogs_cc0`
  - `discogs_restricted` if we ever ingest non-CC0 API fields
- MLCore tier:
  - CC0 catalog subset: `production_approved`
  - restricted subset: `blocked`
- Commercial determination:
  - Discogs catalog metadata in the CC0 categories is viable for commercial
    metadata enrichment.
  - Restricted data is not commercially reusable under the API terms.
- Why:
  - Discogs API terms distinguish CC0 data from restricted data and say
    restricted data may not be used for commercial purposes.
- Allowed uses:
  - genre/style/label enrichment
  - metadata features
  - hard-negative sampling pools
- Recommendation workflows unlocked:
  - style-aware and era-aware neighbors
  - better long-tail related-item retrieval
  - richer explainability facets for hybrid ranking
- Required constraints:
  - exclude user data
  - exclude marketplace data
  - exclude restricted images and any other restricted content
  - keep ingestion limited to fields that Discogs identifies as CC0
- Primary sources:
  - https://support.discogs.com/hc/en-us/articles/360009334593-API-Terms-of-Use
  - https://support.discogs.com/hc/de/articles/360009334593-API-Nutzungsbedingungen

### 6. FMA metadata

- Proposed source id: `fma_metadata`
- MLCore tier: `research_only`
- Commercial determination:
  - The metadata license itself is commercially usable with attribution, but we
    have not yet built the attribution/compliance path or split it cleanly from
    the audio-rights issues. Keep it out of production until that work exists.
- Why:
  - The official FMA dataset repo says metadata is CC BY 4.0.
  - The same repo says the dataset is meant for research purposes.
- Allowed uses:
  - research experimentation
  - evaluation labels
  - prototyping metadata-enriched content models
- Recommendation workflows unlocked:
  - supervised genre/tag structure for content-model development
  - metadata-assisted cold-start experiments
- Required constraints:
  - preserve attribution obligations if later promoted
  - keep metadata and audio as separate manifest sources
- Primary sources:
  - https://github.com/mdeff/fma
  - https://creativecommons.org/licenses/by/4.0/

### 7. FMA audio

- Proposed source id: `fma_audio`
- MLCore tier: `research_only`
- Commercial determination:
  - Not production-safe by default.
- Why:
  - The FMA repo says the dataset distributors do not hold the copyright on the
    audio and distribute tracks under the license chosen by the artist.
  - That means rights are per-track and heterogeneous.
- Allowed uses:
  - content-model research
  - embedding experiments
- Recommendation workflows unlocked:
  - audio-nearest-neighbor retrieval
  - "sounds like this" recommendations
  - cold-start similarity for items with no behavior yet
- Required constraints:
  - per-track license validation before any production consideration
  - never assume a dataset-level blanket commercial right for the audio
- Primary sources:
  - https://github.com/mdeff/fma

### 8. Jamendo catalog and community data

- Proposed source id: `jamendo`
- MLCore tier: `research_only`
- Commercial determination:
  - Conditional and currently too ambiguous for production approval.
- Why:
  - Jamendo API docs expose license-filter fields and repeatedly note that some
    music uses require commercial licensing.
  - The catalog contains Creative Commons material, but production-safe use
    depends on the exact rights of the tracks and the intended product use.
- Allowed uses:
  - research-only metadata and playlist experiments
  - prototyping supplemental explicit/community signals
- Recommendation workflows unlocked:
  - small-scale playlist/radio heuristics
  - review/tag/community-signal experiments
- Required constraints:
  - do not promote Jamendo-trained artifacts to production until legal review
    and rights scope are documented for the exact fields and assets used
- Primary sources:
  - https://developer.jamendo.com/v3.0/docs
  - https://developer.jamendo.com/v3.0/tracks
  - https://developer.jamendo.com/v3.0/radios
  - https://licensing.jamendo.com/legal/termsofuse

### 9. Spotify Million Playlist Dataset

- Proposed source id: `spotify_mpd`
- MLCore tier: `blocked`
- Commercial determination:
  - Not allowed for production or commercial ML use.
- Why:
  - The challenge rules license the Spotify Data only for preparing challenge
    results and say commercial use is prohibited.
- Allowed uses:
  - none in production
  - benchmark use only if we decide that challenge-compliant research work is
    still worth maintaining outside production paths
- Recommendation workflows unlocked:
  - playlist continuation benchmarking
  - candidate-set completion evaluation
  - offline model comparison against a common public baseline
- Required constraints:
  - never let MPD-derived artifacts into production promotion paths
- Primary sources:
  - https://www.aicrowd.com/challenges/spotify-million-playlist-dataset-challenge/challenge_rules

## Implementation Rules For MLCore

1. `backend/mlcore/services/corpus.py` is the enforcement point for source-tier
   policy and production promotion.
2. New external datasets must be added to this matrix before they are added to
   `SOURCE_CLASSIFICATION`.
3. When a source has mixed rights internally, represent it as multiple source
   ids in MLCore rather than one coarse source label.
4. Production promotion requires both:
   - source tier `production_approved`
   - manifest row `allowed_envs` in `production` or `both`
5. Unknown sources stay fail-closed.

## Current Code Alignment

- Code updated on 2026-03-29:
  - `listenbrainz` is now `production_approved`
- Follow-up recommended:
  - split future mixed-rights datasets into separate source ids before ingest
    work begins (`musicbrainz_supplemental`, `discogs_restricted`,
    `fma_metadata`, `fma_audio`, etc.)
