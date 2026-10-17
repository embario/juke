# MLCore Identity Graph Saturation Plan

Updated: 2026-10-17 (overnight investigation on Neptune, read-only)

Supersedes the narrower `tasks/mlcore-spotify-aliases-from-dump-evidence.md` (folded into Phase 2 and Phase 3 below). Builds on `MLCORE_IDENTITY_GRAPH_HYDRATION_DESIGN.md`.

## 1. Summary

The identity graph can gain Spotify track IDs and many more ISRC and MBID links **without any Spotify API calls**, from data already on Neptune:

1. **ListenBrainz listens already carry Spotify track IDs.** In sampled months, 11-22% of listens have a Spotify track ID (`additional_info.spotify_id` or a Spotify `origin_url`, almost all from `music_service=spotify.com`). None of this has ever been stored: ingestion picks MBID, then MSID, then Spotify ID as the identity, and every listen has an MSID, so the Spotify branch never runs. The identity extractor never reads these fields at all.
2. **MusicBrainz already holds Spotify track links for 812,941 recordings** (`mlcore_musicbrainz_recording_url`), which nothing reads.
3. **Shared identifiers are being thrown away instead of used.** The alias table allows one owner per identifier, so the last ListenBrainz ISRC run dropped 2,290,502 of 7,651,613 ISRCs (30%) as "ambiguous" and lost 313,587 more to conflicts. Many of those are several MSIDs (different metadata spellings) for the same recording. Treating a shared Spotify ID (and, more cautiously, a shared ISRC) as same-recording evidence turns those losses into MSID merges.

**The saturation work itself is small on disk: about 28-46 GB of new persistent data (roughly 20-30 GB physical on ZFS), 35-50 GB of short-lived scratch, and about 5 GB of snapshot overhead** (section 4.2). The disk problem on Neptune is elsewhere. Database tablespaces sit on a ZFS dataset with 12-month snapshot retention, so snapshots now hold 4.12 TB, about 1.8x the live data. On top of that, about 1.2 TB (logical) is superseded co-occurrence copies and leftover training scratch. Section 4 lists what can be reclaimed; every item there is an owner decision.

The binding constraint is **random I/O on the HDD mirror**, not space. During this investigation both disks sat at about 92% utilisation and 130 reads/s each, with the 9-day-old incremental listen import competing for them. Section 6 covers scheduling and an NVMe option.

## 2. Current state (measured 2026-10-16/17)

### 2.1 Storage

| Location | Device | Size | Used | Free | Notes |
| --- | --- | ---: | ---: | ---: | --- |
| `/` | NVMe LVM (xfs) | 70 GB | 31 GB | 40 GB | |
| `/home` (incl. `/srv/data` bind, PGDATA) | NVMe LVM (xfs) | 1.8 TB | 972 GB | 790 GB | PGDATA/pg_default ~6 GB. Most of the 972 GB is unexplained (see 4.4). |
| `zfspool/backups` (`/srv/data/backups`) | 2x 9.1 TB HDD mirror, lz4 | 9.09 TB pool | 6.45 TB | 2.52-2.64 TB | 70% capacity, 60% fragmentation. Live data 2.33 TB, **snapshots 4.12 TB**. |

Postgres 18.4, database 3.37 TB logical:

| Tablespace | Physical location | Logical size |
| --- | --- | ---: |
| `juke_mlcore_hot` | ZFS `.../psql-tablespaces/juke_mlcore_hot` (HDD, despite the name) | 806 GB |
| `juke_mlcore_cold` | ZFS `.../psql-tablespaces/juke_mlcore_cold` | 2,560 GB |
| `pg_default` + WAL | NVMe (`/srv/data/juke/postgres-data`) | 6 GB |

ZFS snapshot retention (`/usr/local/sbin/neptune-zfs-snapshot`, `zfs snapshot -r` on the pool): **14 daily, 8 weekly, 12 monthly.** Monthly snapshots are only 4 deep today (July to October), so snapshot space will keep growing until mid-2027. Daily snapshots each pin about 60 GB of churn. Any block a table rewrites or frees stays allocated until every snapshot referencing it expires.

Largest relations:

| Table | Tablespace | Logical total | Role |
| --- | --- | ---: | --- |
| `mlcore_item_cooccurrence` | hot | 668 GB | Live co-occurrence (2.04B pairs, run `3c96bdf9`) |
| `mlcore_listenbrainz_event_ledger` | cold | 665 GB | 1.75B listen events |
| `mlcore_listenbrainz_session_track` | cold | 650 GB | 1.44B session rows |
| `mlcore_cooccurrence_training_pair` | cold | 407 GB | Training staging, finished run |
| `mlcore_item_cooccurrence_v3` | cold | 266 GB | Superseded cold-first build (1.70B pairs); not referenced by code, 0 scans |
| `mlcore_item_cooccurrence_v2` | cold | 266 GB | Same as v3 |
| `mlcore_cooccurrence_training_session_item` | cold | 223 GB | Training staging, finished run |
| `mlcore_canonical_item_alias` | hot | 70 GB | 129.9M rows |
| `mlcore_cooccurrence_training_basket` | cold | 62 GB | Training staging, finished run |
| `mlcore_canonical_item` | hot | 54 GB | 131.75M rows |
| `mlcore_listenbrainz_msid_mbid_mapping` | cold | 18 GB | 24.1M MSID->MBID pairs |
| `mlcore_canonical_item_redirect` | hot | 14 GB | 15.9M rows |

Files: the full ListenBrainz dump (`.tar.zst`, 159 GB) **and** its extracted monthly shards (261 files, 945.5 GB logical, about 384 GB physical at the measured 0.41 lz4 ratio), 15 extracted incremental shard sets, two MusicBrainz `mbdump.tar.bz2` (7.3 GB each).

### 2.2 Identity graph

Counted 2026-10-17 (full scans; the June `mlcore_identity.prom` export is stale):

| Canonical items | Count |
| --- | ---: |
| `recording_msid` | 122,739,689 |
| `recording_mbid` | 11,025,317 |
| `spotify_track` | 1 |

| Aliases (all `active`) | Count | Source |
| --- | ---: | --- |
| `listenbrainz:recording` (MSID) | 112,431,541 | dump ingestion |
| `musicbrainz:recording` (MBID) | 10,924,175 | dump ingestion |
| `isrc:recording` | 6,987,273 | ListenBrainz 5,396,516 (full dump 4,872,690 + incrementals + bridge reruns); MusicBrainz 1,590,757 |
| `spotify:track` | 316,338 | Spotify API hydration (all `match_source=isrc`) |

| Redirects | Active | Conflict | Retired |
| --- | ---: | ---: | ---: |
| `listenbrainz-identity-bridge` (MSID->MBID) | 16,036,630 | 29,027 | 2 |
| `listenbrainz-identity-conflict-resolver` | 35,841 | 1,125 | 3,232 |

MSID->MBID mapping evidence (cold): 15,481,819 active and 8,651,651 conflict rows from the full dump, plus 1,228,144 active from 15 incrementals.

MusicBrainz ISRC bridge (latest `20260627-002124`): 6,090,747 rows, 5,929,945 distinct ISRCs, 5,902,649 recordings. **97.8% of ISRCs map to exactly one recording** (5,796,970); 128,700 map to 2-3; 4,275 to more.

What stands out:

- **Only 13% of MSID items (16.1M of 122.7M) resolve to an MBID.** The rest are bare MSIDs. These are the items the Spotify evidence can reach directly.
- **ISRC coverage is about 5% of canonical items.** MusicBrainz has 5.8M unambiguous ISRCs but contributed only 1.59M aliases, because ListenBrainz claimed many ISRCs first (on MSID items) and because only MBIDs already in the graph can receive one. Phase 6 and the evidence table address both.
- **Spotify coverage is 0.24% of canonical items, all from the API.**

Play-weighted and MusicBrainz-URL overlap samples: COVERAGE_PLACEHOLDER

### 2.3 Pipelines

- Full ListenBrainz identity extraction (MSID->MBID, MSID->ISRC) over all 261 shards took 6.9-8.5 h (June). It writes sorted unique TSVs per shard and stages them in a temp table on the cold tablespace.
- **The incremental listen import is effectively stalled.** Incremental `2669` (2026-09-20) has been importing since Oct 7: 3.0M rows in about 9.4 days. It does per-row dedupe lookups against the 1.75B-row `event_signature` unique index on the HDD pool. The daily identity sync skips a version while its import runs, so identity has been a no-op since Oct 7, and the newest processed listens are from Sep 2.
- A single incremental identity pass took 16 h (Oct 7), dominated by database-side work on the large tables.

### 2.4 Code constraints that shape the design

- `mlcore_canonical_item_alias` is unique on `(source, resource_type, source_id)`: one canonical owner per ISRC and per Spotify ID. That is right for serving lookups, but it can't hold many-to-many evidence.
- `identity_from_listenbrainz_candidates` (`backend/mlcore/services/canonical_items.py`) checks MBID, then MSID, then Spotify ID, so Spotify IDs never reach the graph. `_extract_spotify_id` (`backend/mlcore/ingestion/listenbrainz.py`) returns raw values without URL normalisation and ignores `origin_url`.
- The serving query (`backend/recommender_engine/app/main.py`, `_COOCCURRENCE_SQL`) expands a seed through **one** level of redirect: it gathers items that redirect directly to the seed. Alias resolution follows chains up to 8 deep. Any redirect chain longer than one hop therefore loses co-occurrence neighbours. **New redirects must point directly at the final target**, and existing ones must be repointed when a target is itself redirected. The alternative is to make the expansion recursive.
- Serving returns canonical IDs. A Spotify alias is only useful for output if it sits on the final (post-redirect) canonical item.
- New aliases and redirects take effect at serving time without retraining co-occurrence, because co-occurrence is keyed on the original MSID/MBID canonical IDs and serving maps through redirects.

## 3. Strategy

The order is chosen so each step lands evidence on the best available target, and nothing needs rewriting later.

```text
MusicBrainz Spotify URLs ──► Spotify ↔ MBID   (high confidence, small)
ListenBrainz shards ──► MSID ↔ Spotify, MSID ↔ ISRC, MSID ↔ MBID (with counts)
                          │
                          ▼
              evidence table (many-to-many, cold)
                          │
          cluster MSIDs by dominant Spotify ID
                          │
          target = MBID (via redirect, MB URL, or MB ISRC bridge)
                 else new spotify_track canonical item
                          │
         flat redirects MSID → target, Spotify/ISRC aliases on target
                          │
         hydration queue: mark resolved items matched, seed only the rest
```

### Phase 0: Prerequisites (owner decisions, no data written)

1. **Snapshot policy for database data.** Either (a) cut retention on `zfspool/backups` (for example 7 daily, 4 weekly, 2 monthly) and destroy the oldest monthly snapshots, or (b) carve the Postgres tablespaces into their own child dataset with short retention and protect the small, non-derivable data with `pg_dump` instead. Everything in the MLCore tablespaces is derived from public dumps and can be rebuilt; the irreplaceable data (Juke app tables) lives in `pg_default` on the NVMe and is not in these snapshots at all.
2. **Scratch location.** Put extraction output, `sort` temp files, and a Postgres `temp_tablespaces` / staging tablespace on the NVMe (`/srv/data/juke/...`, 790 GB free, no snapshots, much faster random I/O). Budget 50-100 GB. This keeps transient data out of snapshots entirely.
3. **Pause the incremental listen import while bulk identity phases run**, or accept that both run at a fraction of normal speed. It is barely progressing anyway (section 2.3).
4. **Serving fix:** make `_COOCCURRENCE_SQL` seed expansion follow redirect chains (recursive CTE, depth-limited like alias resolution), or commit to always-flat redirects. Doing both is safest.

### Phase 1: Measure (read-only)

- Per-month profile of Spotify evidence: observations, unique MSID-Spotify pairs, distinct Spotify IDs, MSIDs with several Spotify IDs, Spotify IDs shared by several MSIDs. One month is profiled in this document (section 5.1); extend to a sample of years.
- Overlap of MusicBrainz Spotify-URL recordings with canonical MBID items and with the hydration backlog. Drive the query from the ~813k recordings, not the 6.4M-item queue (the queue-first version timed out).
- Play-weighted coverage baseline (section 2.2) to measure progress against.

### Phase 2: MusicBrainz Spotify URLs to aliases

- Parse Spotify track IDs from `mlcore_musicbrainz_recording_url` (latest source version; track URLs only; handle `intl-xx/` paths and query strings; validate 22-character base62).
- Recording MBID -> canonical item, following redirects to the final target. One Spotify ID per recording: active alias on the target with `match_source='musicbrainz_url'`. Several IDs per recording: store as evidence only.
- Never overwrite an alias owned by another canonical item; count conflicts.
- Mark matching `ProviderHydrationItem` rows `matched` (skip leased rows).

### Phase 3: ListenBrainz evidence extraction (one pass, schema v3)

- Extend `extract_listenbrainz_identity_shard` to emit, per shard, **with observation counts** (`sort | uniq -c` instead of `sort -u`):
  - `msid \t spotify_track_id \t n` from `spotify_id`, `spotify_track_id`, and Spotify `origin_url`, normalised.
  - `msid \t isrc \t n` (today's ISRC output, which is deleted after materialisation and has no counts).
  - `msid \t mbid` (unchanged).
  - Optional: counts of other provider IDs (Apple Music, Deezer, YouTube) for later; cheap to collect.
- Bump `EXTRACTION_SCHEMA_VERSION` to 3 so all shards replay once (the mechanism used for ISRC).
- Write outputs zstd-compressed to NVMe scratch. Run over the full dump shards plus the 15 extracted incrementals, at the measured ~7-9 h.
- Fix ingestion so future listens keep the Spotify ID as evidence: keep the MSID as the identity, but record the normalised Spotify ID in the same incremental pass.

### Phase 4: Evidence table (cold)

New table, for example `mlcore_identity_evidence`: `(subject_canonical_item_id, scheme, value, source, source_version, observation_count, shard_count, first_seen, last_seen)`, unique on `(scheme, value, subject_canonical_item_id, source)`, with an index on `(scheme, value)`. Schemes: `spotify_track`, `isrc`, `mbid`, `url:<provider>`. This is the many-to-many store the alias table cannot be. Aliases remain the serving index: exactly one active owner per identifier, chosen from evidence by explicit rules. Load from the Phase 3 files with `COPY` into a staging table on the NVMe temp tablespace, then aggregate into the evidence table in batches.

### Phase 5: Cluster and resolve

For each MSID, find its dominant Spotify ID: at least 90% of its Spotify observations and at least 2 observations. MSIDs without a dominant ID are left alone. Group MSIDs by dominant Spotify ID `S`, then for each group:

1. Resolve each MSID to its current final target (MBID via existing redirect, else itself).
2. Choose the target, in order:
   - exactly one MBID among the group's resolved targets, **or** a MusicBrainz URL link `S -> MBID` from Phase 2, **or** the group's dominant ISRC maps to exactly one MBID in `mlcore_musicbrainz_recording_isrc`;
   - otherwise a new `spotify_track:S` canonical item (the design doc's preference order is MBID > spotify_track > MSID).
   - If the group resolves to several different MBIDs, record a conflict and do nothing.
3. Write a **flat** redirect from every not-yet-redirected MSID in the group to the target (`source='listenbrainz-spotify-cluster'`, lean evidence; detail stays in the evidence table). Never change an existing active redirect; disagreement becomes a counted conflict.
4. Upsert the Spotify alias `S` on the target, and ISRC aliases where the ISRC now has a single owner after clustering.
5. When a `spotify_track` item later gains an MBID (new MusicBrainz data), redirect it to the MBID and repoint its inbound redirects directly at the MBID in the same transaction (keeps chains one hop).

Guardrails: cap group size (for example 200 MSIDs) and route larger groups to review; sample-audit about 200 merges against MusicBrainz metadata before bulk activation; everything runs in batches with progress metrics and is idempotent.

### Phase 6: ISRC saturation

- Re-materialise ListenBrainz ISRC evidence with counts into the evidence table.
- For MSIDs or clusters still without an MBID, bridge via MusicBrainz ISRC only when the ISRC maps to exactly one recording MBID. That produces new MSID->MBID redirects without any ListenBrainz-side mapping.
- Keep one-owner ISRC aliases for unambiguous ISRCs; everything else stays queryable in the evidence table.

### Phase 7: Hydration and serving integration

- Mark hydration items whose canonical item (after redirect) has a Spotify alias as `matched` with `resolved_by` evidence, and make seeding skip them. The remaining API budget, already constrained by the shared account quota, then goes to popularity-ranked items that have no offline answer (fleet task, Part 2).
- Track play-weighted coverage of MBID, ISRC, and Spotify as the headline metric, alongside whole-catalogue counts.

### Phase 8: Keep it current

- The incremental pipeline carries the same extraction (Phase 3 changes) and runs Phase 5 on the delta.
- MusicBrainz releases re-run Phase 2 and the ISRC bridge.
- Separately (not in this plan): the incremental listen import needs a redesign; at 4 rows/s it cannot keep up.

## 4. Disk budget

### 4.1 Unit costs (measured from live tables)

| Table | Logical bytes per row (incl. indexes) |
| --- | ---: |
| `mlcore_canonical_item_alias` | 581 |
| `mlcore_canonical_item` | 437 |
| `mlcore_canonical_item_redirect` | 949 (heavy evidence JSON; ~300 with lean evidence) |
| `mlcore_listenbrainz_msid_mbid_mapping` | 809 |
| `mlcore_provider_hydration_item` | 420 |

Physical on ZFS is roughly logical / 1.5 (dataset compress ratio 1.61). Shard JSON compresses to 0.41.

### 4.2 Saturation work

Volumes use the extrapolation in section 5.1 (25-40M MSID-Spotify pairs, 20-35M distinct Spotify IDs). Phase 1 replaces them with measured figures before any write.

**Persistent (stays after the work):**

| Artifact | Rows (est.) | Bytes/row | Logical | Tablespace |
| --- | ---: | ---: | ---: | --- |
| Evidence table: Spotify + ISRC + MusicBrainz URL pairs with counts | 37-52M | ~250 | 9-13 GB | cold |
| Spotify aliases (one owner per Spotify ID) | 20-34M | 581 | 12-20 GB | hot |
| Cluster redirects (secondary MSIDs to target) | 3-6M | 949 (or ~300 lean) | 3-6 GB (1-2 lean) | hot |
| ISRC-bridge redirects (MSID to MBID via unique MusicBrainz ISRC) | 2-5M | 949 (or ~300 lean) | 2-5 GB (0.6-1.5 lean) | hot |
| New `spotify_track` canonical items (multi-MSID groups without MBID) | 2-4M | 437 | 1-2 GB | hot |
| MusicBrainz-URL Spotify aliases | ~0.8M | 581 | ~0.5 GB | hot |
| **Total** | | | **~28-46 GB logical (~19-31 GB physical)** | |

Singleton groups (one MSID per Spotify ID, the 97% case) need no new canonical item and no redirect: the alias goes on the MSID's current final target.

**Transient (peak during the work, then deleted):**

| Artifact | Peak | Where |
| --- | ---: | --- |
| Per-shard extraction output with counts (Spotify, ISRC; MBID files already exist, ~6.5 GB) | ~23 GB raw, ~6-8 GB zstd | NVMe scratch |
| `sort` temp (4 shards in parallel) | 4-8 GB | NVMe scratch |
| `COPY` staging tables before aggregation | 20-26 GB | NVMe temp tablespace |
| Index builds on evidence and alias tables | 5-8 GB | same tablespace as the table |
| WAL bursts | bounded by `max_wal_size` | NVMe (PGDATA) |
| **Peak** | **~35-50 GB** | |

**Snapshot amplification.** Appends cost no extra snapshot space. Rewrites do: marking up to ~7M hydration items matched (~3 GB), updates to aliases and redirects, and `VACUUM` all leave old blocks pinned for the snapshot lifetime. Budget about 5 GB pinned. **If staging runs on the ZFS tablespaces instead of NVMe, add 20-26 GB pinned for up to 12 months** (the next monthly snapshot captures it). That is the main reason for Phase 0.2.

**Bottom line:** the work needs about 20-30 GB of physical HDD space, 35-50 GB of NVMe scratch, and roughly 5 GB of snapshot overhead. Today's 2.5 TB free on the pool and 790 GB on the NVMe cover it many times over. The capacity risk is snapshot growth from everything else, not this plan.

### 4.3 Reclaimable space (owner decisions)

| Item | Logical | Est. physical | Freed when | Risk |
| --- | ---: | ---: | --- | --- |
| Snapshot retention cut on `zfspool/backups` | n/a | up to ~4 TB (shared blocks) | when old snapshots are destroyed | Loses point-in-time copies of the dump files and database; the database contents are rebuildable from dumps, and these snapshots are crash-consistent at best |
| `mlcore_item_cooccurrence_v2`, `_v3` | 572 GB | ~355 GB | after DROP **and** the snapshots that reference them expire | Superseded builds; not referenced by code; 0 scans since stats reset. Confirm no one plans to swap them in |
| Training staging (`..._training_pair`, `_session_item`, `_basket`) | 743 GB | ~460 GB | after TRUNCATE and snapshot expiry | Rows of finished run `3c96bdf9` (128/128 buckets merged and scored). The next training run recreates them. Use TRUNCATE, not DELETE |
| Extracted ListenBrainz shards (full dump) | 945 GB | ~384 GB | after delete and snapshot expiry | Needed for the Phase 3 pass. Delete afterwards; the 159 GB `.tar.zst` can regenerate them (hours) |
| Docker unused images/build cache | | ~17 GB | after snapshot expiry (Docker root is on ZFS) | Rebuild cost only |

**Ordering matters:** dropping or deleting anything on `zfspool/backups` frees nothing until the snapshots that reference it are gone. With today's 12-month monthly retention that is mid-2027. The snapshot decision comes first, or none of the rest helps in the near term.

### 4.4 Unexplained NVMe usage

`/home` reports 972 GB used, but PGDATA (~6 GB) and the readable home-directory contents don't come close. Docker's active root is `/srv/data/backups/docker-root` (on ZFS, ~30 GB), not the NVMe. Two likely causes, neither verified (both need root):

1. **An old Docker root.** `/home/mario/.srv-root/docker` (root-only, on the NVMe) looks like the Docker data-root from before it moved to ZFS. Old images and volumes there, including any earlier Postgres volume, would still occupy the NVMe. Check: `sudo du -xsh /home/mario/.srv-root/docker`.
2. **Files hidden under the ZFS mount.** `/srv/data` is a bind mount of `/home/mario/.srv-root/data`, and the ZFS dataset mounts on top of `/srv/data/backups`. Anything written there while the pool was not mounted sits on the NVMe, hidden. Check: `sudo mount --bind /home /mnt/home-raw && sudo du -xsh /mnt/home-raw/mario/.srv-root/data/backups`.

If either holds most of the ~930 GB, the NVMe has far more room than it appears, which matters for the scratch and NVMe-tablespace options in sections 3 and 6.

## 5. Evidence profile

### 5.1 One full month (2025-06 shard)

Full pass over `listens/2025/6.listens` (8.2 GB, 85 s of CPU once I/O was available):

| Measure | Value |
| --- | ---: |
| Listens | 14,534,464 |
| Listens with a Spotify track ID | 2,668,668 (18.4%) |
| Unique MSID-Spotify pairs | 775,102 |
| Distinct Spotify IDs | 753,142 |
| MSIDs with a Spotify ID | 760,918 |
| MSIDs with more than one Spotify ID | 13,043 (1.7%); 1,684 of them have a 90% dominant ID |
| Spotify IDs seen with exactly 1 / 2 / 3 / 4+ MSIDs | 733,707 / 17,736 / 1,352 / 347 |
| Unique MSID-ISRC pairs | 605,524 |
| Unique MSID-MBID pairs (embedded mapping) | 509,281 |
| MSIDs with both a Spotify ID and an embedded MBID | 65,345 (8.6% of Spotify MSIDs) |

What this means for the design:

- **Within a month, MSID and Spotify ID are almost one-to-one** (97.4% of Spotify IDs have a single MSID). Most of the value is a direct Spotify alias for an MSID (or for its MBID target), not merging.
- Merges come from the 2.6% of Spotify IDs shared by several MSIDs. Across all months this share will be higher, because spelling variants accumulate over time.
- MSIDs with several Spotify IDs are rare and usually have no dominant ID. They are left unresolved, as intended.
- Only 8.6% of Spotify-tagged MSIDs carry an embedded MBID in the same listen, so MBID targets will mostly come from existing redirects (15.5M MSIDs), MusicBrainz URLs, and the ISRC bridge. Phase 1 measures that overlap.

**Extrapolation to the full dump** (to be replaced by Phase 1 numbers): about 15% of 1.75B listens carry Spotify IDs, so roughly 260M observations. The previous ISRC run turned 116.9M observations into 11.4M unique pairs (9.8%). Within-month repetition is lower (29%), so expect **25-40M unique MSID-Spotify pairs and roughly 20-35M distinct Spotify track IDs**. That is several times the 6.4M-item API hydration backlog.

### 5.2 Samples (first 200,000 listens of each file)

| Month | Spotify track ID | ISRC | Embedded recording MBID |
| --- | ---: | ---: | ---: |
| 2026-02 | 22.0% | 22.6% | 10.5% |
| 2025-06 | 18.0% | 12.3% | 6.1% |
| 2023-06 | 21.1% | 12.3% | 1.9% |
| 2019-06 | 11.4% | 2.2% | 15.2% |

Nearly all Spotify IDs come from `music_service=spotify.com` (the ListenBrainz Spotify importer). First-200k samples are not random within a month; treat them as indicative.

### 5.3 Previous ISRC run (full dump, June)

116,899,336 ISRC observations; 11,426,875 unique MSID-ISRC pairs; 7,651,613 distinct ISRCs; 5,046,564 aliases materialised; 2,290,502 ISRCs dropped as ambiguous; 313,587 lost to existing-alias conflicts.

## 6. Time and I/O

- Phase 3 extraction: one sequential pass over ~384 GB physical of shards. The June run took 6.9-8.5 h; expect similar if the incremental import is paused, much longer if not.
- Phases 4-6: bulk `COPY` and set-based joins against the canonical item (54 GB), alias (70 GB), and redirect (14 GB) tables. On the HDD pool these are random-I/O bound (130 reads/s per disk observed). Expect hours per phase, consistent with the 16-hour incremental identity pass.
- **NVMe option:** moving the three identity-graph tables (~138 GB today, ~170-200 GB after saturation) to a new NVMe tablespace (`ALTER TABLE ... SET TABLESPACE`, which rewrites and locks each table) would cut these phases and serving lookups by an order of magnitude. It costs NVMe space the owner previously had to free, and removes those tables from ZFS snapshots (acceptable: they are derived data).

## 7. Policy note

These Spotify identifiers come from ListenBrainz and MusicBrainz data, not from Spotify's API. Spotify's Developer Policy restricts using Spotify content to train ML models (III.14). How MLCore uses provider identifiers is an owner judgement; this plan only stores identifiers for linking.

## 8. Open questions for the owner

1. Snapshot policy (Phase 0.1): cut retention, or split the database into its own dataset?
2. Approve NVMe scratch (Phase 0.2) and, separately, an NVMe tablespace for the identity graph (section 6)?
3. Pause the incremental listen import during bulk phases?
4. Drop `mlcore_item_cooccurrence_v2`/`_v3` and truncate training staging?
5. Merge policy: accept Spotify-ID clustering with the guardrails in Phase 5, after a sample audit?
