# B6 Spotify cluster operator runbook

Track B ships code only. Only the Neptune operator runs these commands, using the existing
backend container and its established environment. Fleet agents do not deploy, run management
commands on Neptune, touch `/srv/juke-dev`, or restart hydration. Refs #249; depends on B7 #258's
shared redirect writer. No Spotify API calls occur.

## Preconditions and merge policy

Complete Phase 1 measurement and B5 precision check; finish B3 extraction and B4 loading.
Freeze evidence loading, MusicBrainz imports, incremental imports and other redirect/alias writers
for the run and any resume. Use an explicit MusicBrainz release and an operator-selected evidence
snapshot/run identifier; do not change either on resume. Keep the hydration worker paused.
Provision the existing NVMe temp tablespace and check free scratch space before staging.

All commands default to **dry-run and 1%**. The sample hashes the Spotify ID so every member of a
selected group is included. Only MSIDs with >=2 observations and >=90% Spotify dominance qualify.
Groups above 200 members go to the review JSONL. Any disagreement between resolved MBIDs, B5 URL
MBIDs, and a unique MB ISRC candidate skips the group. Existing aliases owned elsewhere and existing
active redirects are never overwritten. Promoting an existing `spotify_track` root to an MBID
repoints its inbound edges in the same transaction through the shared writer.

The literal paths below are **inside the backend container**. Replace the release, run identifier
and NVMe tablespace with the measured operator values; choose a mounted audit directory so exports
and checkpoints survive container replacement. No new environment or secret file is required.

## 1% dry-run and audit

```bash
docker compose exec -T backend python manage.py cluster_spotify_identity \
  --musicbrainz-version MB_RELEASE --source-version B4_SNAPSHOT \
  --sample-percent 1 --dry-run --batch-size 50000 \
  --staging-tablespace NVME_TEMP_TABLESPACE \
  --audit-export /audit/b6-one-percent.jsonl --audit-limit 200 \
  --review-export /audit/b6-one-percent-review.jsonl \
  --explain-export /audit/b6-one-percent-plans.json
```

Review the EXPLAIN output before writes: the main staging/resolution/ownership statements must
show sequential scans with hash joins, no nested-loop index probes. Group counts, per-batch action
rows/second and ETA go to stderr; the JSON summary goes to stdout. Dry-run redirect/repoint counts
are upper bounds; the writer skips already-existing edges on actual insert.

The audit contains up to 200 proposed redirects, chosen deterministically by hash from the 1% slice,
including source MSID, resolved root, proposed canonical key, target reason, counts, evidence
versions/dates/shard counts, MusicBrainz ISRC/URL records, MusicBrainz and ListenBrainz links, and
local title/artist/release metadata when available. The legacy raw-listen table often has no rows;
missing descriptive metadata is explicit (`metadata_missing=true`). **Do not count such rows as
completed metadata audits.** For each proposed merge compare the source ListenBrainz title/artist
with MusicBrainz (or the sibling MSIDs for a Spotify-only group), including versions/live/remixes.

If titles/artists are absent, supply a small offline JSONL supplement extracted from the local
ListenBrainz/MusicBrainz dumps (no Spotify requests), then repeat the dry run with
`--audit-metadata /audit/b6-metadata.jsonl`. Each line is an object like:

```json
{"canonical_key":"recording_msid:MSID", "title":"Title", "artist":"Artist", "source":"ListenBrainz dump/version"}
{"canonical_key":"recording_mbid:MBID", "title":"Title", "artist":"Artist", "source":"MusicBrainz dump/version"}
```

The supplemental objects and provenance are preserved in the audit. For Spotify-only targets,
use `spotify_track:ID` as the target supplement key after checking all member MSIDs. If fewer than
200 merges appear, the operator must obtain an adequate sample before requesting full-run approval;
do not infer approval or increase the write percentage automatically.

## Bounded 1% write and resume

After inspecting dry-run conflicts/plans, run the same arguments with `--write` instead of
`--dry-run`, plus `--resume-state /audit/b6-one-percent-state.json`. `--max-batches 1` optionally
limits initial validation. On interruption rerun the **identical** command and paths, removing
`--max-batches` to finish. Do not change the evidence/bridge snapshot. An advisory lock prevents
concurrent B6 runners. Checkpoints advance after a committed batch via atomic file replacement;
a crash before checkpoint persistence repeats an idempotent batch. Staging is rebuilt on resume.
Original audit files are preserved once a saved cursor exists.

Retain the original audit, review list and summary. The operator audits about 200 merges, reports
findings and obtains **explicit owner approval** before the full run. The flag below is an operator
attestation of that decision; it does not grant approval. Any write above 1% is rejected without it.

## Full run (only after owner approval)

Use the same command with `--sample-percent 100 --write --owner-approved-full-run` and **new**
full-run audit/review/plan/state paths. Keep `--batch-size 50000`; supported bounds are 10000..100000
staged action rows per transaction. The shared writer also repoints any pre-staged inbound edges
atomically; their fan-in can exceed the action batch size. New items/Spotify aliases are bounded
by the action slice; ISRC aliases are assigned to their first action and protected by
`ON CONFLICT DO NOTHING`. Existing one-owner ISRC aliases are retained; an ISRC with any evidence
subject outside the cluster is conservatively skipped unless all evidence already has one owner.

There is no measured production B6 runtime yet. Budget **several hours (roughly 2–8 h or longer)**
for 1% staging/audit on the HDD pool, since sampling still scans large evidence, canonical, redirect
and alias tables. A full run may take **8–24+ h** depending on I/O contention and write volume.
These are planning estimates, not benchmarks. Use reported throughput/ETA for the write portion;
phase messages identify staging scans, whose time is not included in that ETA. Resume repeats the
staging scans. No resource-heavy training runs are involved.

## Small-fixture validation

`backend/tests/unit/test_spotify_clusters.py` covers dominance boundaries, each target path,
ambiguous ISRC fallback, MBID contradictions, aliases and existing active edges, cycle depth,
flat root promotion, cap/review output, whole-group sampling, dry-run, interruption/replay,
metadata supplementation, checkpoint parameter validation and hash-join EXPLAIN assertions.

Local checks use an isolated PostgreSQL fixture database; CI runs the complete Django suite.
No Docker was run on Uranus and nothing was run on Neptune by the fleet.
