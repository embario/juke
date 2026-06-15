from __future__ import annotations

import hashlib
import json
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import UUID

from django.db import connection, transaction
from django.utils import timezone

from mlcore.models import ListenBrainzIdentityShard, SourceIngestionRun

BRIDGE_SOURCE_ID = 'listenbrainz-identity-bridge'
PAIR_STAGE_TABLE = 'mlcore_listenbrainz_identity_pair_stage'
DEFAULT_OUTPUT_ROOT = '/srv/data/backups/juke/listenbrainz/identity-evidence'
PROGRESS_INTERVAL_ROWS = 1_000_000


@dataclass(frozen=True)
class ListenBrainzIdentityBridgeResult:
    run_id: str
    source_version: str
    shard_count: int
    source_row_count: int
    mapped_row_count: int
    unique_pair_count: int
    malformed_row_count: int
    active_mapping_count: int
    conflict_msid_count: int
    redirect_count: int
    redirect_conflict_count: int
    elapsed_seconds: float


@dataclass(frozen=True)
class ShardExtractionResult:
    shard_key: str
    output_path: str
    source_row_count: int
    mapped_row_count: int
    unique_pair_count: int
    malformed_row_count: int
    skipped: bool = False


def import_listenbrainz_identity_bridge(
    manifest_path: str | Path,
    *,
    output_root: str | Path | None = None,
    max_shards: int | None = None,
    force: bool = False,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> ListenBrainzIdentityBridgeResult:
    started = time.monotonic()
    manifest_path = Path(manifest_path)
    manifest = _load_manifest(manifest_path)
    source_version = str(manifest['source_version'])
    shard_root = manifest_path.parent
    target_root = Path(output_root or DEFAULT_OUTPUT_ROOT) / source_version
    target_root.mkdir(parents=True, exist_ok=True)
    shards = list(manifest['shards'])
    if max_shards is not None:
        if max_shards < 1:
            raise ValueError('max_shards must be greater than zero')
        shards = shards[:max_shards]

    fingerprint = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if force:
        with transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                'DELETE FROM mlcore_listenbrainz_msid_mbid_mapping WHERE source_version = %s',
                [source_version],
            )
            ListenBrainzIdentityShard.objects.filter(source_version=source_version).delete()
    run = SourceIngestionRun.objects.create(
        source=BRIDGE_SOURCE_ID,
        import_mode='full',
        source_version=source_version,
        raw_path=str(manifest_path),
        checksum=fingerprint,
        fingerprint=fingerprint,
        status='running',
        policy_classification='production_approved',
        metadata={
            'phase': 'extract',
            'manifest_path': str(manifest_path),
            'output_root': str(target_root),
            'shard_count': len(shards),
            'completed_shards': 0,
            'processed_bytes': 0,
            'total_bytes': sum(int(shard.get('size_bytes') or 0) for shard in shards),
            'tablespaces': {'evidence': 'juke_mlcore_cold', 'redirects': 'juke_mlcore_hot'},
        },
    )
    totals = {
        'source_row_count': 0,
        'mapped_row_count': 0,
        'unique_pair_count': 0,
        'malformed_row_count': 0,
        'processed_bytes': 0,
    }
    try:
        for index, shard in enumerate(shards, start=1):
            source_path = shard_root / str(shard['relative_path'])
            result = extract_listenbrainz_identity_shard(
                source_path,
                source_version=source_version,
                shard_key=str(shard['relative_path']),
                source_sha256=str(shard.get('sha256') or ''),
                output_root=target_root,
                force=force,
                progress_callback=progress_callback,
            )
            _load_shard_pairs(result, source_version=source_version, source_sha256=str(shard.get('sha256') or ''))
            totals['source_row_count'] += result.source_row_count
            totals['mapped_row_count'] += result.mapped_row_count
            totals['unique_pair_count'] += result.unique_pair_count
            totals['malformed_row_count'] += result.malformed_row_count
            totals['processed_bytes'] += int(shard.get('size_bytes') or 0)
            elapsed = max(time.monotonic() - started, 0.001)
            metadata = {
                **run.metadata,
                'phase': 'extract',
                'completed_shards': index,
                'current_shard': result.shard_key,
                'processed_bytes': totals['processed_bytes'],
                'source_row_count': totals['source_row_count'],
                'mapped_row_count': totals['mapped_row_count'],
                'unique_pair_count': totals['unique_pair_count'],
                'malformed_row_count': totals['malformed_row_count'],
                'throughput_bytes_per_second': totals['processed_bytes'] / elapsed,
                'eta_seconds': _eta_seconds(
                    processed=totals['processed_bytes'],
                    total=int(run.metadata['total_bytes']),
                    elapsed=elapsed,
                ),
            }
            SourceIngestionRun.objects.filter(pk=run.pk).update(
                source_row_count=totals['source_row_count'],
                imported_row_count=totals['unique_pair_count'],
                malformed_row_count=totals['malformed_row_count'],
                metadata=metadata,
            )
            run.metadata = metadata
            _report(progress_callback, {'event': 'shard_complete', 'shard_index': index, **metadata})

        SourceIngestionRun.objects.filter(pk=run.pk).update(metadata={**run.metadata, 'phase': 'materialize'})
        summary = _classify_and_materialize(source_version)
        elapsed_seconds = time.monotonic() - started
        final_metadata = {
            **run.metadata,
            **summary,
            **totals,
            'phase': 'complete',
            'elapsed_seconds': elapsed_seconds,
            'completed_shards': len(shards),
        }
        SourceIngestionRun.objects.filter(pk=run.pk).update(
            status='succeeded',
            source_row_count=totals['source_row_count'],
            imported_row_count=summary['active_mapping_count'],
            duplicate_row_count=max(totals['unique_pair_count'] - summary['active_mapping_count'], 0),
            canonicalized_row_count=summary['redirect_count'],
            unresolved_row_count=summary['active_mapping_count'] - summary['redirect_count'],
            malformed_row_count=totals['malformed_row_count'],
            metadata=final_metadata,
            completed_at=timezone.now(),
        )
        return ListenBrainzIdentityBridgeResult(
            run_id=str(run.id),
            source_version=source_version,
            shard_count=len(shards),
            source_row_count=totals['source_row_count'],
            mapped_row_count=totals['mapped_row_count'],
            unique_pair_count=totals['unique_pair_count'],
            malformed_row_count=totals['malformed_row_count'],
            elapsed_seconds=elapsed_seconds,
            **summary,
        )
    except Exception as exc:
        SourceIngestionRun.objects.filter(pk=run.pk).update(
            status='failed',
            source_row_count=totals['source_row_count'],
            imported_row_count=totals['unique_pair_count'],
            malformed_row_count=totals['malformed_row_count'],
            metadata={**run.metadata, **totals},
            last_error=str(exc),
            completed_at=timezone.now(),
        )
        raise


def extract_listenbrainz_identity_shard(
    source_path: str | Path,
    *,
    source_version: str,
    shard_key: str,
    source_sha256: str,
    output_root: str | Path,
    force: bool = False,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> ShardExtractionResult:
    source_path = Path(source_path)
    if not source_path.is_file():
        raise FileNotFoundError(f'ListenBrainz shard does not exist: {source_path}')
    output_path = Path(output_root) / f'{shard_key}.msid-mbid.tsv'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoint = ListenBrainzIdentityShard.objects.filter(
        source_version=source_version,
        shard_key=shard_key,
    ).first()
    if (
        not force
        and checkpoint is not None
        and checkpoint.status == 'succeeded'
        and checkpoint.source_sha256 == source_sha256
        and output_path.is_file()
    ):
        return ShardExtractionResult(
            shard_key=shard_key,
            output_path=str(output_path),
            source_row_count=checkpoint.source_row_count,
            mapped_row_count=checkpoint.mapped_row_count,
            unique_pair_count=checkpoint.unique_pair_count,
            malformed_row_count=checkpoint.malformed_row_count,
            skipped=True,
        )

    checkpoint, _ = ListenBrainzIdentityShard.objects.update_or_create(
        source_version=source_version,
        shard_key=shard_key,
        defaults={
            'source_sha256': source_sha256,
            'output_path': str(output_path),
            'status': 'running',
            'source_row_count': 0,
            'mapped_row_count': 0,
            'unique_pair_count': 0,
            'malformed_row_count': 0,
            'completed_at': None,
            'last_error': '',
        },
    )
    temp_path = output_path.with_suffix(output_path.suffix + '.part')
    temp_path.unlink(missing_ok=True)
    sort_tmp = output_path.parent / '.sort-tmp'
    sort_tmp.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, 'LC_ALL': 'C'}
    process = subprocess.Popen(
        ['sort', '-u', '-T', str(sort_tmp), '-o', str(temp_path)],
        stdin=subprocess.PIPE,
        text=True,
        encoding='utf-8',
        env=env,
    )
    source_rows = 0
    mapped_rows = 0
    malformed_rows = 0
    try:
        assert process.stdin is not None
        with source_path.open('rb') as source:
            for raw_line in source:
                source_rows += 1
                try:
                    payload = json.loads(raw_line)
                    pair = _extract_pair(payload)
                except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError):
                    malformed_rows += 1
                    continue
                if pair is not None:
                    mapped_rows += 1
                    process.stdin.write(f'{pair[0]}\t{pair[1]}\n')
                if source_rows % PROGRESS_INTERVAL_ROWS == 0:
                    _report(progress_callback, {
                        'event': 'extract_progress',
                        'shard_key': shard_key,
                        'source_row_count': source_rows,
                        'mapped_row_count': mapped_rows,
                        'malformed_row_count': malformed_rows,
                    })
        process.stdin.close()
        return_code = process.wait()
        if return_code:
            raise RuntimeError(f'sort failed for {shard_key} with exit code {return_code}')
        unique_pairs = _count_lines(temp_path)
        temp_path.replace(output_path)
        ListenBrainzIdentityShard.objects.filter(pk=checkpoint.pk).update(
            status='running',
            source_row_count=source_rows,
            mapped_row_count=mapped_rows,
            unique_pair_count=unique_pairs,
            malformed_row_count=malformed_rows,
        )
        return ShardExtractionResult(
            shard_key=shard_key,
            output_path=str(output_path),
            source_row_count=source_rows,
            mapped_row_count=mapped_rows,
            unique_pair_count=unique_pairs,
            malformed_row_count=malformed_rows,
        )
    except Exception as exc:
        if process.poll() is None:
            process.kill()
            process.wait()
        temp_path.unlink(missing_ok=True)
        ListenBrainzIdentityShard.objects.filter(pk=checkpoint.pk).update(
            status='failed',
            source_row_count=source_rows,
            mapped_row_count=mapped_rows,
            malformed_row_count=malformed_rows,
            last_error=str(exc),
            completed_at=timezone.now(),
        )
        raise


def _extract_pair(payload: dict[str, Any]) -> tuple[str, str] | None:
    metadata = payload.get('track_metadata') or {}
    additional = metadata.get('additional_info') or {}
    mapping = metadata.get('mbid_mapping') or {}
    msid = payload.get('recording_msid') or metadata.get('recording_msid') or additional.get('recording_msid')
    mbid = mapping.get('recording_mbid') or additional.get('recording_mbid')
    if not msid or not mbid:
        return None
    return str(UUID(str(msid))), str(UUID(str(mbid)))


def _load_shard_pairs(result: ShardExtractionResult, *, source_version: str, source_sha256: str) -> None:
    checkpoint = ListenBrainzIdentityShard.objects.get(source_version=source_version, shard_key=result.shard_key)
    if checkpoint.status == 'succeeded' and checkpoint.source_sha256 == source_sha256:
        return
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(f'TRUNCATE TABLE {PAIR_STAGE_TABLE}')
        _copy_pair_file(cursor, Path(result.output_path))
        cursor.execute(
            f'''
            INSERT INTO mlcore_listenbrainz_msid_mbid_mapping (
                recording_msid,
                recording_mbid,
                source_version,
                shard_observation_count,
                first_shard,
                last_shard,
                status,
                created_at,
                updated_at
            )
            SELECT recording_msid, recording_mbid, %s, 1, %s, %s, 'active', NOW(), NOW()
            FROM {PAIR_STAGE_TABLE}
            ON CONFLICT (recording_msid, recording_mbid, source_version) DO UPDATE
            SET shard_observation_count = mlcore_listenbrainz_msid_mbid_mapping.shard_observation_count + 1,
                last_shard = EXCLUDED.last_shard,
                updated_at = NOW()
            ''',
            [source_version, result.shard_key, result.shard_key],
        )
        ListenBrainzIdentityShard.objects.filter(pk=checkpoint.pk).update(
            status='succeeded',
            source_sha256=source_sha256,
            output_path=result.output_path,
            source_row_count=result.source_row_count,
            mapped_row_count=result.mapped_row_count,
            unique_pair_count=result.unique_pair_count,
            malformed_row_count=result.malformed_row_count,
            completed_at=timezone.now(),
            last_error='',
        )


def _copy_pair_file(cursor, path: Path) -> None:
    sql = f'COPY {PAIR_STAGE_TABLE} (recording_msid, recording_mbid) FROM STDIN'
    raw_cursor = getattr(cursor, 'cursor', cursor)
    with path.open('r', encoding='utf-8', newline='') as handle:
        if hasattr(raw_cursor, 'copy_expert'):
            raw_cursor.copy_expert(sql, handle)
            return
    raise RuntimeError('ListenBrainz identity bridge requires PostgreSQL COPY support')


def _classify_and_materialize(source_version: str) -> dict[str, int]:
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            '''
            UPDATE mlcore_listenbrainz_msid_mbid_mapping
            SET status = 'active', updated_at = NOW()
            WHERE source_version = %s
            ''',
            [source_version],
        )
        cursor.execute(
            '''
            WITH conflicts AS (
                SELECT recording_msid
                FROM mlcore_listenbrainz_msid_mbid_mapping
                WHERE source_version = %s
                GROUP BY recording_msid
                HAVING COUNT(DISTINCT recording_mbid) > 1
            )
            UPDATE mlcore_listenbrainz_msid_mbid_mapping mapping
            SET status = 'conflict', updated_at = NOW()
            FROM conflicts
            WHERE mapping.source_version = %s
              AND mapping.recording_msid = conflicts.recording_msid
            ''',
            [source_version, source_version],
        )
        cursor.execute(
            '''
            SELECT COUNT(*)
            FROM mlcore_listenbrainz_msid_mbid_mapping
            WHERE source_version = %s AND status = 'active'
            ''',
            [source_version],
        )
        active_mapping_count = int(cursor.fetchone()[0])
        cursor.execute(
            '''
            SELECT COUNT(DISTINCT recording_msid)
            FROM mlcore_listenbrainz_msid_mbid_mapping
            WHERE source_version = %s AND status = 'conflict'
            ''',
            [source_version],
        )
        conflict_msid_count = int(cursor.fetchone()[0])

        candidates_sql = '''
            SELECT
                source_item.id AS from_id,
                target_item.id AS to_id,
                mapping.recording_msid,
                mapping.recording_mbid,
                mapping.shard_observation_count
            FROM mlcore_listenbrainz_msid_mbid_mapping mapping
            JOIN mlcore_canonical_item source_item
              ON source_item.canonical_key = 'recording_msid:' || mapping.recording_msid::text
            JOIN mlcore_canonical_item target_item
              ON target_item.canonical_key = 'recording_mbid:' || mapping.recording_mbid::text
            WHERE mapping.source_version = %s
              AND mapping.status = 'active'
        '''
        cursor.execute(
            f'''
            UPDATE mlcore_canonical_item_redirect redirect
            SET status = 'retired',
                updated_at = NOW()
            WHERE redirect.source = %s
              AND redirect.source_version = %s
              AND redirect.status = 'active'
              AND NOT EXISTS (
                  SELECT 1
                  FROM ({candidates_sql}) candidate
                  WHERE candidate.from_id = redirect.from_canonical_item_id
                    AND candidate.to_id = redirect.to_canonical_item_id
              )
            ''',
            [BRIDGE_SOURCE_ID, source_version, source_version],
        )
        cursor.execute(
            f'''
            INSERT INTO mlcore_canonical_item_redirect (
                from_canonical_item_id,
                to_canonical_item_id,
                relation,
                confidence,
                source,
                source_version,
                status,
                evidence,
                created_at,
                updated_at
            )
            SELECT
                candidate.from_id,
                candidate.to_id,
                'same_recording',
                1.0,
                %s,
                %s,
                'active',
                jsonb_build_object(
                    'recording_msid', candidate.recording_msid,
                    'recording_mbid', candidate.recording_mbid,
                    'shard_observation_count', candidate.shard_observation_count
                ),
                NOW(),
                NOW()
            FROM ({candidates_sql}) candidate
            ON CONFLICT (from_canonical_item_id) DO UPDATE
            SET status = CASE
                    WHEN mlcore_canonical_item_redirect.to_canonical_item_id = EXCLUDED.to_canonical_item_id
                    THEN 'active'
                    ELSE 'conflict'
                END,
                confidence = CASE
                    WHEN mlcore_canonical_item_redirect.to_canonical_item_id = EXCLUDED.to_canonical_item_id
                    THEN EXCLUDED.confidence
                    ELSE mlcore_canonical_item_redirect.confidence
                END,
                source_version = EXCLUDED.source_version,
                evidence = CASE
                    WHEN mlcore_canonical_item_redirect.to_canonical_item_id = EXCLUDED.to_canonical_item_id
                    THEN EXCLUDED.evidence
                    ELSE mlcore_canonical_item_redirect.evidence || jsonb_build_object(
                        'conflicting_target_id', EXCLUDED.to_canonical_item_id
                    )
                END,
                updated_at = NOW()
            ''',
            [BRIDGE_SOURCE_ID, source_version, source_version],
        )
        cursor.execute(
            '''
            SELECT COUNT(*) FILTER (WHERE status = 'active'),
                   COUNT(*) FILTER (WHERE status = 'conflict')
            FROM mlcore_canonical_item_redirect
            WHERE source = %s AND source_version = %s
            ''',
            [BRIDGE_SOURCE_ID, source_version],
        )
        redirect_count, redirect_conflict_count = (int(value) for value in cursor.fetchone())
    return {
        'active_mapping_count': active_mapping_count,
        'conflict_msid_count': conflict_msid_count,
        'redirect_count': redirect_count,
        'redirect_conflict_count': redirect_conflict_count,
    }


def _load_manifest(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f'ListenBrainz shard manifest does not exist: {path}')
    manifest = json.loads(path.read_text(encoding='utf-8'))
    if manifest.get('source') != 'listenbrainz':
        raise ValueError(f'Unexpected ListenBrainz manifest source: {manifest.get("source")!r}')
    if not manifest.get('source_version') or not isinstance(manifest.get('shards'), list):
        raise ValueError('ListenBrainz manifest is missing source_version or shards')
    return manifest


def _count_lines(path: Path) -> int:
    count = 0
    with path.open('rb') as handle:
        for count, _ in enumerate(handle, start=1):
            pass
    return count


def _eta_seconds(*, processed: int, total: int, elapsed: float) -> float | None:
    if processed <= 0 or total <= processed:
        return 0.0 if total <= processed else None
    return (total - processed) / (processed / elapsed)


def _report(callback: Callable[[dict[str, Any]], None] | None, payload: dict[str, Any]) -> None:
    if callback:
        callback(payload)
