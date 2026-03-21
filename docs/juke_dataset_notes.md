# Juke Dataset Research Notes (Markdown Conversion)

## Detailed notes on the top 8

## 1) ListenBrainz full dumps

This is the strongest public interaction dataset for Juke’s current stack because it gives you timestamped implicit feedback at scale, monthly JSON listen files, and MusicBrainz-linked identities you can normalize immediately. It supports:

- User-track bipartite modeling
- Item-item co-occurrence
- Next-item/session approximations
- Recency-aware splits
- Hard-negative generation

The main caution is privacy and ethics: it is public opt-in listen history, so strip user-facing profile fields early, use only pseudonymous IDs internally, and avoid re-identification or sensitive inference workflows.

## 2) ListenBrainz incremental dumps

These are what make ListenBrainz production-like instead of just an academic snapshot. After a full bootstrap, you can replay incrementals into your event store and retrain or refresh co-occurrence graphs and LTR examples on a schedule.

One operational caveat: deletions are not represented in incrementals, so a perfectly accurate mirror still requires periodic full re-imports. This is manageable and worth building around.

## 3) MusicBrainz canonical dumps

For your current `juke_id + Spotify-ID` world, this is the cleanest bridge into a durable open identity layer. The canonical dump is explicitly positioned by MetaBrainz as useful for recommendation because it collapses many duplicate or near-equivalent releases/recordings into canonical representatives.

In practice, this is the single best way to prevent training-data fragmentation before you build co-occurrence matrices or content embeddings.

## 4) MusicBrainz PostgreSQL dumps

These are the richest source for production-safe open metadata: artists, releases, recordings, relationships, tags, and external-link scaffolding.

The catch is licensing granularity and engineering overhead:
- Core metadata is CC0
- Some supplementary fields are non-commercial/share-alike

For a production corpus, whitelist only CC0 tables/columns. Operationally, PostgreSQL import is heavier than JSON or canonical CSV, but provides the strongest long-term metadata backbone.

## 5) Discogs monthly dumps

Discogs is the best open complement to MusicBrainz for release-level metadata enrichment:
- genres
- styles
- labels
- editions
- catalog disambiguation

It is not a behavioral dataset, so it will not directly improve collaborative rankers. It is useful for:
- metadata overlap
- cold-start features
- hard-negative mining within stylistic neighborhoods

The monthly dump cadence makes it easier to maintain than API-only approaches.

## 6) FMA

FMA is one of the most practical open-audio corpora for the embedding phase because it provides:
- full-length audio
- genres
- tags
- artist text
- catalog structure

It supports content models and retrieval benchmarks.

Weak point: licensing heterogeneity:
- metadata is CC BY 4.0
- audio follows per-track artist licenses
- intended for research

So treat as pretraining/evaluation corpus unless you enforce strict production-compatible per-track rights filtering.

## 7) Jamendo API catalog / playlists / reviews

Jamendo is a low-friction way to get an open-ish catalog with:
- tracks
- tags
- playlists
- review scores/text
- community signals

Low-friction for small teams, but legal/operational tradeoffs:
- API access is rate-limited
- commercial licensing rules are explicit

Best as bootstrap/enrichment source unless a production license is secured.

## 8) Spotify MPD

MPD is strong for public playlist-co-occurrence benchmarking, but not production-safe training.

Challenges:
- terms restrict challenge use, ban commercial use
- playlist data is randomized, filtered, and includes fictitious tracks

Best for offline benchmark (playlist continuation and co-occurrence model selection), not serving model foundation.

---

## Per-dataset fit against requested criteria

## ListenBrainz full dumps

- **Basic details**: official MetaBrainz dataset, full dump archives, user listens plus public/stats data, updated twice monthly. Broad page mentions daily incrementals.
- **Training quality**: strong implicit feedback, excellent user-track graph, good for recency splits, pseudo-sessions, and cold-start checks after canonicalization. No audio.
- **Preprocessing**: medium load (MBID resolution, dedupe, privacy stripping). Events are timestamped and monthly-sharded.
- **Licensing/compliance**: CC0, redistribution and commercial use allowed. Train on aggregated/pseudonymous IDs only.
- **Practicality**: no API key required, high-volume but manageable; ingest recent years first.
- **Relevance**: **Excellent**.

## ListenBrainz incremental dumps

- **Basic details**: same schema as full dump; supports freshness updates.
- **Training quality**: ideal for rolling retrains, popularity drift, and time-based validation. Not standalone; operationally append to full import.
- **Licensing/compliance**: same CC0 + privacy cautions.
- **Practicality**: very strong for pipelines, keep rolling window on laptop and periodic full reconciliation.
- **Relevance**: **Excellent**.

## MusicBrainz canonical dumps

- **Basic details**: zstd CSV dumps (twice monthly), intended to simplify reasoning over representative entities.
- **Training quality**: no interaction events, but improves normalization quality for all downstream ranking and cold-start eval.
- **Licensing/compliance**: CC0, commercial use allowed.
- **Practicality**: simple load and crosswalk creation.
- **Relevance**: **Excellent**.

## MusicBrainz PostgreSQL dumps

- **Basic details**: full metadata mirror, includes relationships/community metadata.
- **Training quality**: valuable for metadata rankers and graph features; no direct feedback events.
- **Licensing/compliance**: core CC0; core + supplementary split carefully to avoid CC BY-NC-SA fields.
- **Practicality**: best on cloud or dedicated DB; heavy for laptop-first unless subset.
- **Relevance**: **Excellent** long term, **Good** immediate bootstrapping.

## Discogs monthly dumps

- **Basic details**: XML dumps for releases/artists/labels/masters.
- **Training quality**: strong for metadata enrichment, not for collaborative graph.
- **Licensing/compliance**: dumps are CC0; prefer dumps over API for production.
- **Practicality**: strong batch target, pair with MusicBrainz.
- **Relevance**: **Good**.

## Jamendo API catalog / playlists / reviews

- **Basic details**: hundreds of thousands tracks, playlists, reviews, tags, library actions.
- **Training quality**: useful for co-occurrence-like signals and metadata training, not volume-scale collaborative events.
- **Licensing/compliance**: good for prototyping; commercial use not blanket-safe.
- **Practicality**: easy to start, but pagination/rate limits.
- **Relevance**: **Medium** overall, **Good** for low-friction bootstrap.

## FMA

- **Basic details**: 106,574 tracks, 917 GiB, genres/tags/bios/audio subsets.
- **Training quality**: no large user-track graph; strong for embeddings and cold-start evaluation.
- **Licensing/compliance**: metadata CC BY 4.0, audio per-track artist licenses.
- **Practicality**: use small/medium locally, full corpus in cloud.
- **Relevance**: **Good** for embeddings, **Medium** for full hybrid stack.

## Spotify MPD

- **Basic details**: 1M playlists (2010–2017), playlist-track metadata.
- **Training quality**: excellent benchmark for playlist continuation, not production behavioral corpus.
- **Licensing/compliance**: challenge-only, no commercial use, no redistribution/re-identification.
- **Practicality**: easy once access granted.
- **Relevance**: **Low** for production, **Excellent** benchmark.

---

## Shortlists

### A) Best 3 to start with for fastest time-to-train

1. **ListenBrainz full dumps** — immediate collaborative graph and timestamps.
2. **MusicBrainz canonical dumps** — fastest cleanup of IDs before training.
3. **FMA** — quickest open-audio source for OpenL3/content phase (start with small/medium subsets).

### B) Best 3 for long-term quality / production robustness

1. **ListenBrainz full + incremental dumps** — ongoing behavior feed.
2. **MusicBrainz canonical + PostgreSQL core CC0 tables** — identity + metadata backbone.
3. **Discogs monthly dumps** — durable metadata enrichment.

### C) Recommended Phase 1.5 hybrid plan (free/public + low-friction)

Use:

- ListenBrainz full + incrementals for user-item events
- MusicBrainz canonical + core metadata for identity and features
- FMA small/medium + OpenMIC / AcousticBrainz for content pretraining and cold-start validation
- Add Discogs for metadata enrichment after first trainer works
- Use MPD only offline for benchmark

---

## Concrete mapping plan for shortlisted datasets

### ListenBrainz

**Improves**: co-occurrence ranker, negative sampling for LTR, later hybrid ranker.

**Map to Juke**

- raw ingest: `staging.listenbrainz_listens_raw`
- normalized events: `events.user_track_events`
- sessionized view: `features.session_events`
- graph tables: `features.item_item_cooccurrence`, `features.user_item_implicit`

**Minimal extracted fields**

- `user_id` = ListenBrainz user ID or hashed username surrogate
- `track_id` = recording MBID
- `item_timestamp` = listen timestamp
- `session_context` = derived from inactivity gap or same-client window
- `event_type` = `listen`
- side metadata = artist/release MBIDs, optional client metadata

**Fallback enrichment**

1. Resolve MBIDs to canonical MBIDs via MusicBrainz canonical dump.
2. Then attempt optional Spotify crosswalk for unresolved items.
3. Avoid primary dependence on Spotify backfill due to modern policy friction.

### MusicBrainz canonical + core metadata

**Improves**: metadata ranker, embedding joins, hybrid feature hygiene.

**Map to Juke**

- `identity.musicbrainz_recording`
- `identity.musicbrainz_release`
- `identity.musicbrainz_artist`
- `identity.canonical_recording_map`
- `identity.external_id_map`

Use it to resolve favorites-by-name and search history entities. Build canonical `juke_item_id` keyed by MBIDs, with Spotify IDs as adapters.

### FMA

**Improves**: embedding phase and cold-start evaluation.

**Map to Juke**

- `corpus.open_audio_tracks`
- `corpus.open_audio_files`
- `features.audio_embeddings_open`
- `features.tag_supervision_open`

**Suggested path**

1. Start with FMA-medium/small locally.
2. Compute OpenL3 embeddings.
3. Train/fine-tune content tower.
4. Evaluate retrieval by genre/artist/tag.
5. Distill embeddings into candidate features for items with sparse behavior.

**Missing pieces**

- no large user-item graph
- no Spotify IDs
- production use requires license filtering

### Discogs

**Improves**: metadata ranker and hard-negative mining for LTR.

**Map to Juke**

- `enrichment.discogs_artist`
- `enrichment.discogs_release`
- `enrichment.discogs_master`
- `features.item_style_tags`

Use style/genre/label as ranking features and as near-miss negative sampling strategy.

### OpenMIC / AcousticBrainz (optional)

- **OpenMIC**: instrument-label supervision. Map to `features.audio_tag_supervision`.
- **AcousticBrainz**: precomputed descriptors by MBID. Map to `features.audio_descriptors_bootstrap`.

Treat AcousticBrainz as temporary; it is static post-2022.

---

## Best 90-day path to first trained hybrid model

1. Adopt MBID-first identity.
   - Set `juke_item_id` anchored to canonical MusicBrainz recording/release/artist IDs.
   - Keep Spotify IDs in crosswalk table.
2. Bootstrap collaborative training from ListenBrainz full dumps:
   - user-item implicit matrix
   - item-item co-occurrence counts
   - recency-weighted session transitions
   - user-time holdout train/val/test
3. Use MusicBrainz core + Discogs for metadata features:
   - artist overlap
   - release-group overlap
   - genre/style
   - label
   - country/era
   - tag counts
4. Train embeddings on FMA-medium first:
   - compute OpenL3 vectors
   - evaluate content retrieval
   - inject similarity as candidate feature in hybrid ranker
5. Build LTR examples:
   - positives = listened/favorited
   - negatives = random popular, same-artist-not-played, same-style-not-played, same-session skip-proxy when available
6. Use MPD only for offline playlist continuation benchmarking.

---

## Best production-grade path for next 6 months

Center production corpus on:

- ListenBrainz + MusicBrainz + Discogs

Keep FMA/OpenMIC/AcousticBrainz in model-building only unless licenses are clearly compatible.

Treat Jamendo as optional licensed expansion rather than default dependency.

This avoids identity lock-in on restrictive proprietary adapters.

---

## Risks + mitigations

### Risk 1: ID fragmentation across Spotify IDs, text favorites, and open datasets

**Mitigation**
- Canonical MBID-first identity.
- Maintain scored crosswalk to Spotify via ISRC + artist/title/album matching.
- Manual review buckets for ambiguous matches.

### Risk 2: Training on non-production-safe data

**Mitigation**
- Partition corpus: `production_safe`, `research_only`, `license_required`.
- Gate each training job by policy.
- MPD-like datasets should not train production-serving models.

### Risk 3: User-generated data privacy

**Mitigation**
- Hash/surrogate user IDs and strip usernames.
- Publish internal ethics notes.
- Avoid inference of protected traits.
- Periodically refresh full dumps because incrementals lack deletions.

### Risk 4: Over-reliance on Spotify enrichment

**Mitigation**
- Use Spotify only as secondary adapter.
- Cache approved results aggressively.

### Risk 5: Embedding corpus mismatch

**Mitigation**
- Pretrain on open audio and fine-tune on behavioral corpus.
- Do not rely solely on content embeddings for rank quality.
- Separate cold-start and warm-start evaluation.
