# Juke ML Dataset Report

## Scope and objective

This report compares candidate datasets for building a production-minded hybrid music recommender (behavioral + metadata + content). It focuses on how useful each source is for:

- collaborative ranking from implicit feedback
- metadata/knowledge features
- content embeddings for cold-start
- legal and operational feasibility

Date: March 19, 2026.

## Executive summary

The practical production backbone should be:

1. **ListenBrainz full + incremental dumps** (behavioral interactions)
2. **MusicBrainz canonical dumps** (identity normalization)
3. **MusicBrainz PostgreSQL metadata core** (graph + feature engineering)
4. **Discogs monthly dumps** (enrichment for style/genre/label features)
5. **FMA** (content model pretraining)
6. **Spotify MPD** (offline benchmark only)
7. **Jamendo** (optional bootstrap/enrichment source with licensing awareness)

## Full comparison table

| Dataset | Data type | Cadence / freshness | Size / format | ML relevance for hybrid ranking | Compliance and ops notes | Download links |
|---|---|---|---|---|---|---|
| **ListenBrainz full dumps** | User-item listens + optional stats | Full snapshots twice monthly, plus periodic refresh; supported by incrementals | Large monthly JSON-like exports under MetaBrainz mirror | Very high for collaborative ranking, implicit positives, recency modeling, co-occurrence and LTR labeling | CC0; requires privacy protection, pseudonymous user IDs, and profile field stripping | [ListenBrainz dumps docs](https://listenbrainz.readthedocs.io/en/latest/users/listenbrainz-dumps.html), [MetaBrainz ListenBrainz directory](https://data.metabrainz.org/pub/musicbrainz/listenbrainz/fullexport/) |
| **ListenBrainz incrementals** | Newly submitted listen events only | Daily replay for near-real-time refresh usage (with full snapshot as source of truth) | Incremental event slices matching full dump schema | High for freshness refresh and rolling validation; not standalone (use with full dump) | Same CC0 and privacy constraints; deletions are not represented in incrementals | [MetaBrainz ListenBrainz incremental directory](https://data.metabrainz.org/pub/musicbrainz/listenbrainz/incremental/) |
| **MusicBrainz canonical dumps** | Canonicalized artist/recording/release identifiers | Updated frequently via MetaBrainz snapshots (commonly bi-monthly) | `tar.zst` CSV bundle | Very high for deduping IDs before training, stable item keys, better graph quality | CC0; one of the safest legal options in this stack | [MusicBrainz canonical page](https://musicbrainz.org/doc/Canonical_MusicBrainz_data), [MetaBrainz canonical directory](https://data.metabrainz.org/pub/musicbrainz/canonical_data/) |
| **MusicBrainz PostgreSQL dumps** | Full catalog metadata graph and relationships | Frequent snapshot cadence (commonly biweekly) | PostgreSQL-compatible SQL-formatted data for full ingest | High for metadata ranker features (artist/release relationships, tags, crosswalks) | Core is CC0, supplemental tables can be CC BY-NC-SA; feature-gate by policy table/field | [MusicBrainz DB download docs](https://musicbrainz.org/doc/MusicBrainz_Database/Download), [MetaBrainz MusicBrainz dir](https://data.metabrainz.org/pub/musicbrainz/) |
| **Discogs monthly dumps** | Release/artist/label/style/genre metadata | Monthly XML dumps | XML archives | Medium-high for feature enrichment and hard-negative sampling; no direct user behavior | CC0 for dump files; useful but not a primary collaborative source | [Discogs data index](https://discogs-data-dumps.s3.us-west-2.amazonaws.com/index.html), [Discogs developers](https://www.discogs.com/developers/) |
| **FMA (Free Music Archive dataset)** | Audio + metadata + tags + splits | Static public snapshot | `fma_small`, `fma_medium`, `fma_large`, `fma_full` archives | High for content embedding pretraining; low for collaborative ranking by itself | Metadata CC BY 4.0; audio tracks have per-track license conditions | [FMA repo](https://github.com/mdeff/fma), [FMA data files](https://os.unil.cloud.switch.ch/fma/) |
| **Jamendo API catalog / playlists / reviews** | API tracks, playlists, reviews, tags, user actions | API-driven, pagination-dependent; manageable but rate-limited | JSON APIs | Medium for bootstrapping and tag/review-aware enrichment; limited direct collaborative depth | Terms and licensing vary by use case; often non-commercial without agreement | [Jamendo API docs](https://developer.jamendo.com/v3.0/docs), [Jamendo docs/terms](https://developer.jamendo.com/v3.0/docs) |
| **Spotify MPD** | Large playlist co-occurrence benchmark | Static challenge dataset release | JSON files | Medium: useful for playlist continuation benchmarking, **not** production training | Challenge-style restrictions and non-commercial terms; synthetic/filtered data characteristics | [AIcrowd challenge page](https://www.aicrowd.com/challenges/spotify-million-playlist-dataset-challenge), [Zenodo mirror](https://zenodo.org/records/6425593) |

## Detailed technical notes

### 1) ListenBrainz full dumps

**What it provides**
- Timestamped implicit feedback at scale (user listens)
- MBID-rich identifiers in common schemas
- Strong basis for user-item matrix construction and chronological splits

**ML use in Juke**
- User-item implicit matrix
- Item-item co-occurrence counts
- Session-aware transitions
- Negative sample candidate design for LTR

**Preprocessing burden**
- Normalize users (hash/surrogate)
- MBID resolution + canonical mapping
- Duplicate handling across re-imports
- Privacy scrubbing of profile-level fields

**Where it helps most**
- Warm-start retrieval and reranking
- Session-aware features and recency-weighted scoring

---

### 2) ListenBrainz incrementals

**What it provides**
- New interaction events after bootstrap from full dumps

**ML use in Juke**
- Weekly/monthly model refresh
- Concept-drift tracking
- Rolling-window validation and ranking updates

**Key operational caveat**
- Deletions are not included, so periodic full refresh/rebuild is still required

**How to use safely**
- Use idempotent appenders
- Keep source timestamp as ground-truth ordering key

---

### 3) MusicBrainz canonical dumps

**What it provides**
- Canonicalized identifiers for recordings/releases/artists

**ML use in Juke**
- Build a stable `juke_item_id` on canonical MBIDs
- Reduce fragmented item representations
- Improve consistency of joins across datasets

**Why it matters**
- Prevents one recording appearing as many IDs in model space
- Improves training stability and long-term metric continuity

---

### 4) MusicBrainz PostgreSQL dumps

**What it provides**
- Full metadata graph with entity and relationship tables

**ML use in Juke**
- Metadata ranker features (artist/release relationships, tags, release context)
- Item enrichment for sparse-interaction tracks
- Crosswalk generation for downstream identifiers

**Preprocessing burden**
- Higher than canonical imports
- Requires schema-aware filtering and table selection
- Must apply license-aware field curation

---

### 5) Discogs monthly dumps

**What it provides**
- Monthly metadata for artists, labels, releases, and style/genre taxonomy

**ML use in Juke**
- Metadata enrichment features
- Hard-negative sampling by style/era while excluding identical artist pairs

**Ops practicality**
- Reliable batch updates, especially for genre/label features
- Good support for long-tail and cold-start candidates

**Limitations**
- No direct collaborative behavior signal

---

### 6) FMA

**What it provides**
- Open music audio + metadata + labels for content model training

**ML use in Juke**
- Pretraining and fine-tuning content vectors (e.g., OpenL3 style pipelines)
- Genre/content proxy supervision
- Supplement for no-history tracks

**Recommended flow**
- Begin with `fma_small` or `fma_medium`
- Evaluate embedding recall on same-genre/same-artist retrieval first
- Inject content features as an auxiliary ranker component

**Compliance reality**
- Not all tracks are production-safe by default
- Apply rights filtering before serving or commercial deployment

---

### 7) Jamendo API catalog / playlists / reviews

**What it provides**
- Lightweight catalog source with community data and review signals

**ML use in Juke**
- Bootstrap metadata and explicit signal experiments

**Tradeoffs**
- Rate limiting and API paging overhead
- Commercial licensing boundaries must be explicitly confirmed
- Use as optional supplemental source unless licensing is secured

---

### 8) Spotify MPD

**What it provides**
- Playlist co-occurrence benchmark corpus

**ML use in Juke**
- Offline benchmarking for playlist continuation and recency heuristics

**Why not production source**
- Restricted challenge terms
- Dataset contains synthetic/randomized/fictitious-track caveats
- Benchmark-only value for model comparison

## Recommended roadmap with these datasets

### Phase A (weeks 1–4)
1. Build MBID-first identity tables from MusicBrainz canonical dumps.
2. Add ListenBrainz full dump ingestion into staging events.
3. Generate user-item implicit events and co-occurrence pairs.
4. Add first LTR feature set from collaborative signals.

### Phase B (weeks 5–8)
1. Add incremental ListenBrainz replay jobs.
2. Add MusicBrainz PostgreSQL metadata features (artist/label/relationship joins).
3. Add Discogs style/genre enrichment and negative sampling pools.
4. Add session/time-aware feature windows and recency weights.

### Phase C (weeks 9–12)
1. Train content model on FMA small/medium.
2. Distill content vectors into hybrid candidate scoring features.
3. Add cold-start and warm-start benchmark split suites.
4. Track compliance tags and feature provenance per training run.

### Ongoing operations
- Use MPD only as offline benchmark.
- Keep Jamendo as optional licensed expansion after core stack is stable.
- Schedule weekly re-ingest sanity checks, monthly full rebuilds if using incrementals.

## Data-risk matrix by production suitability

- **Production-safe primary**: ListenBrainz + MusicBrainz canonical + core PostgreSQL metadata + Discogs enrichers
- **Production-safe with constraints**: FMA (after license filtering)
- **Conditional**: Jamendo (license-dependent)
- **Benchmark-only**: Spotify MPD

## Download/source index

- ListenBrainz dump docs: https://listenbrainz.readthedocs.io/en/latest/users/listenbrainz-dumps.html
- ListenBrainz full + incremental directory: https://data.metabrainz.org/pub/musicbrainz/listenbrainz/
- MusicBrainz canonical data: https://musicbrainz.org/doc/Canonical_MusicBrainz_data
- MusicBrainz canonical mirror: https://data.metabrainz.org/pub/musicbrainz/canonical_data/
- MusicBrainz DB dump docs: https://musicbrainz.org/doc/MusicBrainz_Database/Download
- Discogs data dumps: https://discogs-data-dumps.s3.us-west-2.amazonaws.com/index.html
- FMA dataset: https://github.com/mdeff/fma
- FMA audio/metadata files: https://os.unil.cloud.switch.ch/fma/
- Jamendo API docs: https://developer.jamendo.com/v3.0/docs
- Spotify MPD challenge: https://www.aicrowd.com/challenges/spotify-million-playlist-dataset-challenge
