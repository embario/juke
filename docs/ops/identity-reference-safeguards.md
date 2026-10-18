# Identity reference safeguards

The safeguards in this branch require migration `mlcore.0035` and reviewed deployment. They are not installed in Neptune's live services by writing this document. Keep identity bulk jobs and Spotify hydration paused until the rollout and validation below complete. The 95% gate is unchanged.

## Hold policy

An inactive alias (`conflict` or `retired`), or an alias carrying `metadata.identity_reference_quarantine`, holds its identifier. A Spotify hydration record carrying `evidence.identity_reference_quarantine` holds its ISRC even if no alias exists yet. Raw MusicBrainz and ListenBrainz evidence remains intact.

The shared policy is used by the MusicBrainz ISRC bridge, Spotify clustering, legacy ListenBrainz redirect writers, ISRC alias materialization, hydration/reconciliation, and the MusicBrainz URL reference comparison. A held member vetoes the whole affected cluster, including members that would otherwise disappear during candidate filtering. An unresolved held redirect chain stops promotion conservatively. Retiring a bad reference does not declare the entire recording wrong.

Bulk writers snapshot the hold set during staging. Before each write batch, they take the alias-materialization lock and compare the current set with the snapshot. A difference aborts with an instruction to rebuild staging. New algorithm versions invalidate earlier B5/B6/B7 checkpoints; do not relabel an old run as the new version. Evidence imports and graph writers must still be frozen during a run: this guard is not a replacement for consistent input snapshots.

Hydration checks holds before spending a provider request, then checks them again under the write lock after receiving a result. A same-owner inactive or annotated Spotify alias is never reactivated. Quarantined queue records are not claimed. Source title, complete ordered artist credit, version context and available duration (within two seconds) must agree before an ISRC-derived Spotify alias can be accepted. Explicit master-year differences are held. Missing source metadata is terminal `ambiguous` with a reason, without a provider request; an operator can selectively requeue it after backfill and review. Real metadata contradictions create a durable hold on the queue and the matching ISRC alias. Compatible metadata is corroboration, not independently verified audio identity.

## Source metadata backfill

Migration 0035 adds immutable, cold, source-versioned recording metadata and small partial indexes for the hold policy. Normal future MusicBrainz bridge imports also populate metadata. Existing sources need a separate metadata-only backfill; this does not repeat the ListenBrainz extraction/load or write aliases/redirects.

After reviewed deployment and migration, use the existing local manifest, for each source version still referenced by the hydration queue:

```sh
docker compose exec backend python manage.py import_musicbrainz_recording_metadata \
  --manifest /srv/data/backups/juke/musicbrainz/releases/20260613-002047/manifest.json
docker compose exec backend python manage.py import_musicbrainz_recording_metadata \
  --manifest /srv/data/backups/juke/musicbrainz/releases/20260627-002124/manifest.json
```

The command verifies the archive SHA256, streams `recording` and `artist_credit` into session-local temporary tables, and retains only recordings represented in that release's existing ISRC/URL bridge facts. Stored metadata records the source version and archive checksum. Replays do not overwrite existing metadata; a checksum change for an already stored version is rejected. Missing artists remain unverified. The temporary tables are independent of the original bridge's shared staging and evidence checkpoints.

This is a large archive read with potentially millions of metadata rows. Capacity-review the persistent cold table and temporary database storage before starting; use NVMe temporary tablespaces where configured, run one backfill at a time, and inspect progress/disk headroom. No production-sized timing or space measurement has been claimed for this new command. Do not automatically retry a failed full import by repeating completed evidence loads.

## Validation before resuming

1. Verify all eight existing Spotify and ISRC quarantines and the eight held hydration records remain held.
2. Check source metadata for the eight Herbaliser/Super Numeri conflicts. With mocked or previously saved API results, each must remain held; no live API calls are needed for this check.
3. Verify the Elder and Alok examples, Unicode names, joined credits, missing reference metadata and different master years. Exercise mixed clusters and a hold introduced after staging.
4. Rebuild a bounded dry-run workspace with the new algorithm. Never resume an old checkpoint by editing its algorithm field. Check held-group counts and the EXPLAIN plans before a broader run.
5. Freeze and identify the audit population before selecting a sample. Review supported, contradictory and unverified cases explicitly; keep a blind validation sample. Record source file/line/timestamp and the actual identifiers on the same event. Repeated observations are not independent ground truth.
6. Reassess with the same 95% gate. Reports label the existing comparison as reference agreement, publish held comparisons and the full denominator, and keep held cases out of the success numerator. `eligible_reference_agreement` is informational; it cannot replace the conservative `precision` field used by the existing gate. Do not claim independent precision from matching ISRC strings or selected positive examples.

The existing eight-pair quarantine is already active, with exact before/after snapshots and guarded restore data under `/srv/data/backups/juke/mlcore-handoffs/identity-20261017/remediation/`. Do not automatically restore those rows during a code rollback. No service restart, live migration, metadata backfill, new alias activation or graph promotion is authorized by these operator examples alone.
