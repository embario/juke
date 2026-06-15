---
id: mlcore-musicbrainz-dump-sourcing-storage
title: MLCore MusicBrainz dump sourcing and storage plan
status: review
priority: p1
owner: codex
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - data-ingestion
  - identity
complexity: 2
updated_at: 2026-06-13
---

## Goal

Define and implement the repeatable source-of-truth download path for MusicBrainz dumps needed to enrich MLCore canonical recording identities with ISRCs and any available external URL/platform relationship evidence.

## Scope

- Select the official MusicBrainz full-export artifacts required for `recording_mbid -> isrc`.
- Include URL relationship tables needed to mine Spotify or other platform links where MusicBrainz has them.
- Record expected compressed size, expanded size, checksum verification, and storage path.
- Store raw dumps and extracted staging data in cold storage.
- Add an operator command or script to download, verify, and stage the dump.
- Record source version/date for downstream provenance.

## Out Of Scope

- Transforming dump rows into MLCore aliases beyond basic source manifest/provenance.
- Spotify API resolution.

## Acceptance Criteria

- Download path uses official MetaBrainz/MusicBrainz dump URLs and checksum files.
- Raw dump artifacts land on cold storage, not hot MLCore storage.
- The selected dump version is recorded in the database or run manifest.
- The process can be rerun without corrupting an existing staged dump.
- Documentation names required free disk space before the download starts.

## Execution Notes

- Current official full export checked on 2026-06-09:
  - `mbdump.tar.bz2`: 7 GB compressed.
  - `mbdump-derived.tar.bz2`: 476 MB compressed.
  - `mbdump-edit.tar.bz2`: 15 GB compressed, not expected to be needed for ISRC bridging.
- Use `SHA256SUMS` verification from the same full-export directory.
- Risks:
  - Expanded tables may require substantially more cold storage than compressed files.
  - Dump composition can change over time; guard imports by table presence and schema checks.
- Design reference: `docs/arch/MLCORE_IDENTITY_GRAPH_HYDRATION_DESIGN.md`.

## Handoff

- Completed:
  - Selected official core `mbdump.tar.bz2`; derived and edit-history exports are not required for MBID/ISRC/URL bridging.
  - Added `stage_musicbrainz_dump` discovery, planning, atomic download, SHA-256 verification, required-table validation, cold-storage manifest, and `SourceIngestionRun` provenance.
  - Added rerun/adoption behavior, capacity refusal, partial cleanup, and focused tests.
  - Live plan on 2026-06-13 resolved release `20260613-002047`, 7,260,740,543 compressed bytes, 80 GiB estimated expanded staging, and 100 GiB minimum free space.
  - Verified `/srv/data/backups/juke/musicbrainz` resides on `zfspool/backups` with approximately 7.1 TiB free.
- Next: review and merge, then implement `mlcore-musicbrainz-isrc-bridge-ingestion` against the staged manifest.
- Blockers: none.
