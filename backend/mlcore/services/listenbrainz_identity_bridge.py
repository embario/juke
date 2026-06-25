from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from uuid import UUID

from django.db import connection, transaction
from django.utils import timezone

from mlcore.models import CanonicalItem, ListenBrainzIdentityShard, SourceIngestionRun
from mlcore.services.canonical_items import ITEM_TYPE_RECORDING_MSID, canonical_item_uuid

BRIDGE_SOURCE_ID = 'listenbrainz-identity-bridge'
CONFLICT_RESOLVER_SOURCE_ID = 'listenbrainz-identity-conflict-resolver'
CONFLICT_RESOLVER_POLICY_VERSION = 'shard-dominance-v1'
PAIR_STAGE_TABLE = 'mlcore_listenbrainz_identity_pair_stage'
DEFAULT_OUTPUT_ROOT = '/srv/data/backups/juke/listenbrainz/identity-evidence'
PROGRESS_INTERVAL_ROWS = 1_000_000
EXTRACTION_SCHEMA_VERSION = 2
ISRC_RE = re.compile(r'^[A-Z]{2}[A-Z0-9]{3}[0-9]{7}$')


@dataclass(frozen=True)
class ListenBrainzIdentityBridgeResult:
    run_id: str
    source_version: str
    shard_count: int
    source_row_count: int
    mapped_row_count: int
    unique_pair_count: int
    isrc_observation_count: int
    unique_isrc_pair_count: int
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
    isrc_output_path: str
    source_row_count: int
    mapped_row_count: int
    unique_pair_count: int
    isrc_observation_count: int
    unique_isrc_pair_count: int
    malformed_row_count: int
    skipped: bool = False


@dataclass(frozen=True)
class IdentityGraphExpansionResult:
    source_version: str
    missing_msid_count: int
    created_msid_count: int
    active_mapping_count: int
    conflict_msid_count: int
    redirect_count: int
    redirect_conflict_count: int
    elapsed_seconds: float
    dry_run: bool = False


@dataclass(frozen=True)
class ConflictResolutionResult:
    source_version: str
    policy_version: str
    eligible_conflict_msid_count: int
    resolved_msid_count: int
    created_msid_count: int
    redirect_count: int
    redirect_conflict_count: int
    elapsed_seconds: float
    min_winner_share: float
    min_winner_shards: int
    dry_run: bool = False


@dataclass(frozen=True)
class ISRCAliasMaterializationResult:
    source_version: str
    isrc_observation_count: int
    unique_msid_isrc_pair_count: int
    distinct_isrc_count: int
    materialized_alias_count: int
    ambiguous_isrc_count: int
    existing_alias_conflict_count: int
    unresolved_pair_count: int


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
            'extraction_schema_version': EXTRACTION_SCHEMA_VERSION,
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
        'isrc_observation_count': 0,
        'unique_isrc_pair_count': 0,
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
            totals['isrc_observation_count'] += result.isrc_observation_count
            totals['unique_isrc_pair_count'] += result.unique_isrc_pair_count
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
                'isrc_observation_count': totals['isrc_observation_count'],
                'unique_isrc_pair_count': totals['unique_isrc_pair_count'],
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
            isrc_observation_count=totals['isrc_observation_count'],
            unique_isrc_pair_count=totals['unique_isrc_pair_count'],
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


def expand_listenbrainz_identity_graph(
    source_version: str,
    *,
    batch_size: int = 100_000,
    dry_run: bool = False,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> IdentityGraphExpansionResult:
    if batch_size < 1:
        raise ValueError('batch_size must be greater than zero')
    started = time.monotonic()
    missing_msid_count = _count_missing_msid_canonical_items(source_version)
    created_count = 0
    last_msid = None
    if not dry_run:
        while True:
            msids = _fetch_missing_msid_batch(source_version, batch_size=batch_size, after_msid=last_msid)
            if not msids:
                break
            rows = [
                CanonicalItem(
                    id=canonical_item_uuid(item_type=ITEM_TYPE_RECORDING_MSID, key_value=str(msid)),
                    item_type=ITEM_TYPE_RECORDING_MSID,
                    canonical_key=f'{ITEM_TYPE_RECORDING_MSID}:{msid}',
                )
                for msid in msids
            ]
            CanonicalItem.objects.bulk_create(rows, ignore_conflicts=True, batch_size=batch_size)
            created_count += len(rows)
            last_msid = msids[-1]
            _report(progress_callback, {
                'event': 'msid_canonical_batch',
                'source_version': source_version,
                'batch_size': len(msids),
                'created_msid_count': created_count,
                'missing_msid_count': missing_msid_count,
            })
    summary = {
        'active_mapping_count': 0,
        'conflict_msid_count': 0,
        'redirect_count': 0,
        'redirect_conflict_count': 0,
    }
    if not dry_run:
        summary = _classify_and_materialize(source_version)
    return IdentityGraphExpansionResult(
        source_version=source_version,
        missing_msid_count=missing_msid_count,
        created_msid_count=created_count,
        elapsed_seconds=time.monotonic() - started,
        dry_run=dry_run,
        **summary,
    )


def resolve_listenbrainz_identity_conflicts(
    source_version: str,
    *,
    min_winner_share: float = 0.95,
    min_winner_shards: int = 2,
    policy_version: str = CONFLICT_RESOLVER_POLICY_VERSION,
    batch_size: int = 100_000,
    dry_run: bool = False,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> ConflictResolutionResult:
    if not 0 < min_winner_share <= 1:
        raise ValueError('min_winner_share must be greater than zero and at most one')
    if min_winner_shards < 1:
        raise ValueError('min_winner_shards must be greater than zero')
    if batch_size < 1:
        raise ValueError('batch_size must be greater than zero')
    started = time.monotonic()
    eligible_conflict_msid_count = _count_conflict_msids(source_version)
    resolved_msid_count = _count_resolvable_conflict_msids(
        source_version,
        min_winner_share=min_winner_share,
        min_winner_shards=min_winner_shards,
    )
    created_msid_count = 0
    redirect_count = 0
    redirect_conflict_count = 0
    if not dry_run:
        _write_conflict_resolutions(
            source_version,
            policy_version=policy_version,
            min_winner_share=min_winner_share,
            min_winner_shards=min_winner_shards,
        )
        created_msid_count = _ensure_conflict_resolution_msid_items(
            source_version,
            policy_version=policy_version,
            batch_size=batch_size,
            progress_callback=progress_callback,
        )
        redirect_count, redirect_conflict_count = _materialize_conflict_resolution_redirects(
            source_version,
            policy_version=policy_version,
        )
    return ConflictResolutionResult(
        source_version=source_version,
        policy_version=policy_version,
        eligible_conflict_msid_count=eligible_conflict_msid_count,
        resolved_msid_count=resolved_msid_count,
        created_msid_count=created_msid_count,
        redirect_count=redirect_count,
        redirect_conflict_count=redirect_conflict_count,
        elapsed_seconds=time.monotonic() - started,
        min_winner_share=min_winner_share,
        min_winner_shards=min_winner_shards,
        dry_run=dry_run,
    )


def materialize_listenbrainz_isrc_aliases(source_version: str) -> ISRCAliasMaterializationResult:
    checkpoints = list(
        ListenBrainzIdentityShard.objects.filter(
            source_version=source_version,
            status='succeeded',
            extraction_schema_version__gte=EXTRACTION_SCHEMA_VERSION,
        )
    )
    isrc_paths = [_isrc_output_path(Path(checkpoint.output_path)) for checkpoint in checkpoints]
    isrc_paths = [path for path in isrc_paths if path.is_file()]
    observation_count = sum(checkpoint.isrc_observation_count for checkpoint in checkpoints)
    unique_pair_count = sum(checkpoint.unique_isrc_pair_count for checkpoint in checkpoints)
    if not isrc_paths:
        return ISRCAliasMaterializationResult(
            source_version=source_version,
            isrc_observation_count=observation_count,
            unique_msid_isrc_pair_count=unique_pair_count,
            distinct_isrc_count=0,
            materialized_alias_count=0,
            ambiguous_isrc_count=0,
            existing_alias_conflict_count=0,
            unresolved_pair_count=0,
        )

    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SET LOCAL temp_tablespaces = 'juke_mlcore_cold'")
        cursor.execute('''
            CREATE TEMP TABLE mlcore_lb_isrc_candidate_stage (
                recording_msid uuid NOT NULL,
                isrc varchar(12) NOT NULL
            ) ON COMMIT DROP
        ''')
        for path in isrc_paths:
            _copy_isrc_file(cursor, path)
        cursor.execute('CREATE INDEX ON mlcore_lb_isrc_candidate_stage (recording_msid)')
        cursor.execute('CREATE INDEX ON mlcore_lb_isrc_candidate_stage (isrc)')
        cursor.execute('ANALYZE mlcore_lb_isrc_candidate_stage')

        resolved_cte = '''
            WITH resolved AS (
                SELECT DISTINCT
                    stage.isrc,
                    COALESCE(redirect.to_canonical_item_id, source_item.id) AS canonical_item_id
                FROM mlcore_lb_isrc_candidate_stage stage
                LEFT JOIN mlcore_canonical_item source_item
                  ON source_item.canonical_key = 'recording_msid:' || stage.recording_msid::text
                LEFT JOIN mlcore_canonical_item_redirect redirect
                  ON redirect.from_canonical_item_id = source_item.id
                 AND redirect.status = 'active'
                WHERE source_item.id IS NOT NULL
            ), unambiguous AS (
                SELECT isrc, MIN(canonical_item_id::text)::uuid AS canonical_item_id
                FROM resolved
                GROUP BY isrc
                HAVING COUNT(DISTINCT canonical_item_id) = 1
            )
        '''
        cursor.execute('SELECT COUNT(DISTINCT isrc) FROM mlcore_lb_isrc_candidate_stage')
        distinct_isrc_count = int(cursor.fetchone()[0])
        cursor.execute('''
            SELECT COUNT(*)
            FROM (
                SELECT DISTINCT recording_msid, isrc
                FROM mlcore_lb_isrc_candidate_stage
            ) pairs
        ''')
        unique_pair_count = int(cursor.fetchone()[0])
        cursor.execute('''
            SELECT COUNT(*)
            FROM mlcore_lb_isrc_candidate_stage stage
            LEFT JOIN mlcore_canonical_item source_item
              ON source_item.canonical_key = 'recording_msid:' || stage.recording_msid::text
            WHERE source_item.id IS NULL
        ''')
        unresolved_pair_count = int(cursor.fetchone()[0])
        cursor.execute(
            resolved_cte
            + '''
            SELECT COUNT(*)
            FROM (
                SELECT isrc
                FROM resolved
                GROUP BY isrc
                HAVING COUNT(DISTINCT canonical_item_id) > 1
            ) conflicts
            '''
        )
        ambiguous_isrc_count = int(cursor.fetchone()[0])
        cursor.execute(
            resolved_cte
            + '''
            SELECT COUNT(*)
            FROM unambiguous candidate
            JOIN mlcore_canonical_item_alias alias
              ON alias.source = 'isrc'
             AND alias.resource_type = 'recording'
             AND alias.source_id = candidate.isrc
            WHERE alias.canonical_item_id <> candidate.canonical_item_id
            '''
        )
        existing_alias_conflict_count = int(cursor.fetchone()[0])
        cursor.execute(
            resolved_cte
            + '''
            INSERT INTO mlcore_canonical_item_alias (
                id,
                canonical_item_id,
                source,
                resource_type,
                source_id,
                confidence,
                source_version,
                status,
                metadata,
                created_at,
                updated_at
            )
            SELECT
                md5('isrc:recording:' || candidate.isrc)::uuid,
                candidate.canonical_item_id,
                'isrc',
                'recording',
                candidate.isrc,
                1.0,
                %s,
                'active',
                jsonb_build_object(
                    'match_source', 'listenbrainz',
                    'listenbrainz_source_version', %s
                ),
                NOW(),
                NOW()
            FROM unambiguous candidate
            ON CONFLICT (source, resource_type, source_id) DO UPDATE
            SET confidence = GREATEST(mlcore_canonical_item_alias.confidence, EXCLUDED.confidence),
                status = 'active',
                metadata = mlcore_canonical_item_alias.metadata || EXCLUDED.metadata,
                updated_at = NOW()
            WHERE mlcore_canonical_item_alias.canonical_item_id = EXCLUDED.canonical_item_id
            ''',
            [source_version, source_version],
        )
        materialized_alias_count = max(cursor.rowcount, 0)

    for path in isrc_paths:
        path.unlink(missing_ok=True)
    bridge_run = SourceIngestionRun.objects.filter(
        source=BRIDGE_SOURCE_ID,
        source_version=source_version,
        status='succeeded',
    ).order_by('-completed_at', '-started_at').first()
    if bridge_run is not None:
        bridge_run.metadata = {
            **bridge_run.metadata,
            'isrc_aliases_materialized': True,
            'isrc_alias_summary': {
                'isrc_observation_count': observation_count,
                'unique_msid_isrc_pair_count': unique_pair_count,
                'distinct_isrc_count': distinct_isrc_count,
                'materialized_alias_count': materialized_alias_count,
                'ambiguous_isrc_count': ambiguous_isrc_count,
                'existing_alias_conflict_count': existing_alias_conflict_count,
                'unresolved_pair_count': unresolved_pair_count,
            },
        }
        bridge_run.save(update_fields=['metadata'])
    return ISRCAliasMaterializationResult(
        source_version=source_version,
        isrc_observation_count=observation_count,
        unique_msid_isrc_pair_count=unique_pair_count,
        distinct_isrc_count=distinct_isrc_count,
        materialized_alias_count=materialized_alias_count,
        ambiguous_isrc_count=ambiguous_isrc_count,
        existing_alias_conflict_count=existing_alias_conflict_count,
        unresolved_pair_count=unresolved_pair_count,
    )


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
    isrc_output_path = Path(output_root) / f'{shard_key}.msid-isrc.tsv'
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
        and checkpoint.extraction_schema_version >= EXTRACTION_SCHEMA_VERSION
        and output_path.is_file()
    ):
        return ShardExtractionResult(
            shard_key=shard_key,
            output_path=str(output_path),
            isrc_output_path=str(isrc_output_path),
            source_row_count=checkpoint.source_row_count,
            mapped_row_count=checkpoint.mapped_row_count,
            unique_pair_count=checkpoint.unique_pair_count,
            isrc_observation_count=checkpoint.isrc_observation_count,
            unique_isrc_pair_count=checkpoint.unique_isrc_pair_count,
            malformed_row_count=checkpoint.malformed_row_count,
            skipped=True,
        )

    checkpoint, _ = ListenBrainzIdentityShard.objects.update_or_create(
        source_version=source_version,
        shard_key=shard_key,
        defaults={
            'source_sha256': source_sha256,
            'output_path': str(output_path),
            'extraction_schema_version': EXTRACTION_SCHEMA_VERSION,
            'status': 'running',
            'source_row_count': 0,
            'mapped_row_count': 0,
            'unique_pair_count': 0,
            'isrc_observation_count': 0,
            'unique_isrc_pair_count': 0,
            'malformed_row_count': 0,
            'completed_at': None,
            'last_error': '',
        },
    )
    temp_path = output_path.with_suffix(output_path.suffix + '.part')
    isrc_temp_path = isrc_output_path.with_suffix(isrc_output_path.suffix + '.part')
    temp_path.unlink(missing_ok=True)
    isrc_temp_path.unlink(missing_ok=True)
    sort_tmp = output_path.parent / '.sort-tmp'
    sort_tmp.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, 'LC_ALL': 'C'}
    process = _start_unique_sort(temp_path, sort_tmp=sort_tmp, env=env)
    isrc_process = _start_unique_sort(isrc_temp_path, sort_tmp=sort_tmp, env=env)
    source_rows = 0
    mapped_rows = 0
    isrc_observations = 0
    malformed_rows = 0
    try:
        assert process.stdin is not None
        assert isrc_process.stdin is not None
        with source_path.open('rb') as source:
            for raw_line in source:
                source_rows += 1
                try:
                    payload = json.loads(raw_line)
                    pair, isrc_pairs, invalid_isrc_count = _extract_identity_pairs(payload)
                except (json.JSONDecodeError, UnicodeDecodeError, TypeError, ValueError):
                    malformed_rows += 1
                    continue
                malformed_rows += invalid_isrc_count
                if pair is not None:
                    mapped_rows += 1
                    process.stdin.write(f'{pair[0]}\t{pair[1]}\n')
                for msid, isrc in isrc_pairs:
                    isrc_observations += 1
                    isrc_process.stdin.write(f'{msid}\t{isrc}\n')
                if source_rows % PROGRESS_INTERVAL_ROWS == 0:
                    _report(progress_callback, {
                        'event': 'extract_progress',
                        'shard_key': shard_key,
                        'source_row_count': source_rows,
                        'mapped_row_count': mapped_rows,
                        'isrc_observation_count': isrc_observations,
                        'malformed_row_count': malformed_rows,
                    })
        process.stdin.close()
        isrc_process.stdin.close()
        return_code = process.wait()
        isrc_return_code = isrc_process.wait()
        if return_code or isrc_return_code:
            raise RuntimeError(
                f'sort failed for {shard_key} with exit codes {return_code}/{isrc_return_code}'
            )
        unique_pairs = _count_lines(temp_path)
        unique_isrc_pairs = _count_lines(isrc_temp_path)
        temp_path.replace(output_path)
        isrc_temp_path.replace(isrc_output_path)
        ListenBrainzIdentityShard.objects.filter(pk=checkpoint.pk).update(
            status='running',
            extraction_schema_version=EXTRACTION_SCHEMA_VERSION,
            source_row_count=source_rows,
            mapped_row_count=mapped_rows,
            unique_pair_count=unique_pairs,
            isrc_observation_count=isrc_observations,
            unique_isrc_pair_count=unique_isrc_pairs,
            malformed_row_count=malformed_rows,
        )
        return ShardExtractionResult(
            shard_key=shard_key,
            output_path=str(output_path),
            isrc_output_path=str(isrc_output_path),
            source_row_count=source_rows,
            mapped_row_count=mapped_rows,
            unique_pair_count=unique_pairs,
            isrc_observation_count=isrc_observations,
            unique_isrc_pair_count=unique_isrc_pairs,
            malformed_row_count=malformed_rows,
        )
    except Exception as exc:
        for active_process in (process, isrc_process):
            if active_process.poll() is None:
                active_process.kill()
                active_process.wait()
        temp_path.unlink(missing_ok=True)
        isrc_temp_path.unlink(missing_ok=True)
        ListenBrainzIdentityShard.objects.filter(pk=checkpoint.pk).update(
            status='failed',
            source_row_count=source_rows,
            mapped_row_count=mapped_rows,
            isrc_observation_count=isrc_observations,
            malformed_row_count=malformed_rows,
            last_error=str(exc),
            completed_at=timezone.now(),
        )
        raise


def _start_unique_sort(output_path: Path, *, sort_tmp: Path, env: dict[str, str]) -> subprocess.Popen:
    return subprocess.Popen(
        ['sort', '-u', '-T', str(sort_tmp), '-o', str(output_path)],
        stdin=subprocess.PIPE,
        text=True,
        encoding='utf-8',
        env=env,
    )


def _isrc_output_path(msid_mbid_output_path: Path) -> Path:
    suffix = '.msid-mbid.tsv'
    if not msid_mbid_output_path.name.endswith(suffix):
        raise ValueError(f'Unexpected ListenBrainz identity output path: {msid_mbid_output_path}')
    return msid_mbid_output_path.with_name(
        msid_mbid_output_path.name[:-len(suffix)] + '.msid-isrc.tsv'
    )


def _extract_identity_pairs(
    payload: dict[str, Any],
) -> tuple[tuple[str, str] | None, list[tuple[str, str]], int]:
    metadata = payload.get('track_metadata') or {}
    additional = metadata.get('additional_info') or {}
    mapping = metadata.get('mbid_mapping') or {}
    msid = payload.get('recording_msid') or metadata.get('recording_msid') or additional.get('recording_msid')
    mbid = mapping.get('recording_mbid') or additional.get('recording_mbid')
    normalized_msid = str(UUID(str(msid))) if msid else None
    mbid_pair = (
        (normalized_msid, str(UUID(str(mbid))))
        if normalized_msid and mbid
        else None
    )
    raw_isrcs = additional.get('isrc')
    if raw_isrcs in (None, '') or normalized_msid is None:
        return mbid_pair, [], 0
    if isinstance(raw_isrcs, str):
        raw_isrcs = [raw_isrcs]
    if not isinstance(raw_isrcs, (list, tuple, set)):
        return mbid_pair, [], 1
    isrc_pairs = []
    invalid_isrc_count = 0
    for raw_isrc in raw_isrcs:
        isrc = re.sub(r'[-\s]', '', str(raw_isrc)).upper()
        if not ISRC_RE.fullmatch(isrc):
            invalid_isrc_count += 1
            continue
        isrc_pairs.append((normalized_msid, isrc))
    return mbid_pair, isrc_pairs, invalid_isrc_count


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
            extraction_schema_version=EXTRACTION_SCHEMA_VERSION,
            source_row_count=result.source_row_count,
            mapped_row_count=result.mapped_row_count,
            unique_pair_count=result.unique_pair_count,
            isrc_observation_count=result.isrc_observation_count,
            unique_isrc_pair_count=result.unique_isrc_pair_count,
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


def _copy_isrc_file(cursor, path: Path) -> None:
    sql = 'COPY mlcore_lb_isrc_candidate_stage (recording_msid, isrc) FROM STDIN'
    raw_cursor = getattr(cursor, 'cursor', cursor)
    with path.open('r', encoding='utf-8', newline='') as handle:
        if hasattr(raw_cursor, 'copy_expert'):
            raw_cursor.copy_expert(sql, handle)
            return
    raise RuntimeError('ListenBrainz ISRC alias materialization requires PostgreSQL COPY support')


def _count_missing_msid_canonical_items(source_version: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            '''
            SELECT COUNT(*)
            FROM mlcore_listenbrainz_msid_mbid_mapping mapping
            JOIN mlcore_canonical_item target_item
              ON target_item.canonical_key = 'recording_mbid:' || mapping.recording_mbid::text
            LEFT JOIN mlcore_canonical_item source_item
              ON source_item.canonical_key = 'recording_msid:' || mapping.recording_msid::text
            WHERE mapping.source_version = %s
              AND mapping.status = 'active'
              AND source_item.id IS NULL
            ''',
            [source_version],
        )
        return int(cursor.fetchone()[0])


def _fetch_missing_msid_batch(source_version: str, *, batch_size: int, after_msid: UUID | None = None) -> list[UUID]:
    after_clause = ''
    params: list[Any] = [source_version]
    if after_msid is not None:
        after_clause = 'AND mapping.recording_msid > %s'
        params.append(after_msid)
    params.append(batch_size)
    with connection.cursor() as cursor:
        cursor.execute(
            f'''
            SELECT mapping.recording_msid
            FROM mlcore_listenbrainz_msid_mbid_mapping mapping
            JOIN mlcore_canonical_item target_item
              ON target_item.canonical_key = 'recording_mbid:' || mapping.recording_mbid::text
            LEFT JOIN mlcore_canonical_item source_item
              ON source_item.canonical_key = 'recording_msid:' || mapping.recording_msid::text
            WHERE mapping.source_version = %s
              AND mapping.status = 'active'
              AND source_item.id IS NULL
              {after_clause}
            ORDER BY mapping.recording_msid
            LIMIT %s
            ''',
            params,
        )
        return [row[0] for row in cursor.fetchall()]


def _count_conflict_msids(source_version: str) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            '''
            SELECT COUNT(DISTINCT recording_msid)
            FROM mlcore_listenbrainz_msid_mbid_mapping
            WHERE source_version = %s
              AND status = 'conflict'
            ''',
            [source_version],
        )
        return int(cursor.fetchone()[0])


def _conflict_winners_sql() -> str:
    return '''
        WITH ranked AS (
            SELECT
                mapping.recording_msid,
                mapping.recording_mbid,
                mapping.shard_observation_count,
                SUM(mapping.shard_observation_count) OVER (
                    PARTITION BY mapping.recording_msid
                ) AS total_shard_observation_count,
                COUNT(*) OVER (PARTITION BY mapping.recording_msid) AS candidate_count,
                ROW_NUMBER() OVER (
                    PARTITION BY mapping.recording_msid
                    ORDER BY mapping.shard_observation_count DESC, mapping.recording_mbid
                ) AS candidate_rank
            FROM mlcore_listenbrainz_msid_mbid_mapping mapping
            WHERE mapping.source_version = %s
              AND mapping.status = 'conflict'
        )
        SELECT
            ranked.recording_msid,
            ranked.recording_mbid AS chosen_recording_mbid,
            ranked.shard_observation_count AS winner_shard_observation_count,
            ranked.total_shard_observation_count,
            ranked.candidate_count,
            ranked.shard_observation_count::double precision
                / NULLIF(ranked.total_shard_observation_count, 0)::double precision AS winner_share
        FROM ranked
        JOIN mlcore_canonical_item target_item
          ON target_item.canonical_key = 'recording_mbid:' || ranked.recording_mbid::text
        WHERE ranked.candidate_rank = 1
          AND ranked.shard_observation_count >= %s
          AND ranked.shard_observation_count::double precision
                / NULLIF(ranked.total_shard_observation_count, 0)::double precision >= %s
    '''


def _count_resolvable_conflict_msids(
    source_version: str,
    *,
    min_winner_share: float,
    min_winner_shards: int,
) -> int:
    with connection.cursor() as cursor:
        cursor.execute(
            f'SELECT COUNT(*) FROM ({_conflict_winners_sql()}) winners',
            [source_version, min_winner_shards, min_winner_share],
        )
        return int(cursor.fetchone()[0])


def _write_conflict_resolutions(
    source_version: str,
    *,
    policy_version: str,
    min_winner_share: float,
    min_winner_shards: int,
) -> None:
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(
            '''
            UPDATE mlcore_listenbrainz_msid_mbid_conflict_resolution resolution
            SET status = 'retired',
                updated_at = NOW()
            WHERE resolution.source_version = %s
              AND resolution.policy_version = %s
              AND resolution.status = 'active'
            ''',
            [source_version, policy_version],
        )
        cursor.execute(
            f'''
            INSERT INTO mlcore_listenbrainz_msid_mbid_conflict_resolution (
                recording_msid,
                chosen_recording_mbid,
                source_version,
                policy_version,
                winner_shard_observation_count,
                total_shard_observation_count,
                candidate_count,
                winner_share,
                status,
                evidence,
                created_at,
                updated_at
            )
            SELECT
                winners.recording_msid,
                winners.chosen_recording_mbid,
                %s,
                %s,
                winners.winner_shard_observation_count,
                winners.total_shard_observation_count,
                winners.candidate_count,
                winners.winner_share,
                'active',
                jsonb_build_object(
                    'policy_version', %s,
                    'min_winner_share', %s,
                    'min_winner_shards', %s,
                    'evidence_basis', 'shard_observation_count'
                ),
                NOW(),
                NOW()
            FROM ({_conflict_winners_sql()}) winners
            ON CONFLICT (recording_msid, source_version, policy_version) DO UPDATE
            SET chosen_recording_mbid = EXCLUDED.chosen_recording_mbid,
                winner_shard_observation_count = EXCLUDED.winner_shard_observation_count,
                total_shard_observation_count = EXCLUDED.total_shard_observation_count,
                candidate_count = EXCLUDED.candidate_count,
                winner_share = EXCLUDED.winner_share,
                status = 'active',
                evidence = EXCLUDED.evidence,
                updated_at = NOW()
            ''',
            [
                source_version,
                policy_version,
                policy_version,
                min_winner_share,
                min_winner_shards,
                source_version,
                min_winner_shards,
                min_winner_share,
            ],
        )


def _fetch_conflict_resolution_missing_msid_batch(
    source_version: str,
    *,
    policy_version: str,
    batch_size: int,
    after_msid: UUID | None = None,
) -> list[UUID]:
    after_clause = ''
    params: list[Any] = [source_version, policy_version]
    if after_msid is not None:
        after_clause = 'AND resolution.recording_msid > %s'
        params.append(after_msid)
    params.append(batch_size)
    with connection.cursor() as cursor:
        cursor.execute(
            f'''
            SELECT resolution.recording_msid
            FROM mlcore_listenbrainz_msid_mbid_conflict_resolution resolution
            LEFT JOIN mlcore_canonical_item source_item
              ON source_item.canonical_key = 'recording_msid:' || resolution.recording_msid::text
            WHERE resolution.source_version = %s
              AND resolution.policy_version = %s
              AND resolution.status = 'active'
              AND source_item.id IS NULL
              {after_clause}
            ORDER BY resolution.recording_msid
            LIMIT %s
            ''',
            params,
        )
        return [row[0] for row in cursor.fetchall()]


def _ensure_conflict_resolution_msid_items(
    source_version: str,
    *,
    policy_version: str,
    batch_size: int,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> int:
    created_count = 0
    last_msid = None
    while True:
        msids = _fetch_conflict_resolution_missing_msid_batch(
            source_version,
            policy_version=policy_version,
            batch_size=batch_size,
            after_msid=last_msid,
        )
        if not msids:
            break
        rows = [
            CanonicalItem(
                id=canonical_item_uuid(item_type=ITEM_TYPE_RECORDING_MSID, key_value=str(msid)),
                item_type=ITEM_TYPE_RECORDING_MSID,
                canonical_key=f'{ITEM_TYPE_RECORDING_MSID}:{msid}',
            )
            for msid in msids
        ]
        CanonicalItem.objects.bulk_create(rows, ignore_conflicts=True, batch_size=batch_size)
        created_count += len(rows)
        last_msid = msids[-1]
        _report(progress_callback, {
            'event': 'conflict_msid_canonical_batch',
            'source_version': source_version,
            'policy_version': policy_version,
            'batch_size': len(msids),
            'created_msid_count': created_count,
        })
    return created_count


def _materialize_conflict_resolution_redirects(source_version: str, *, policy_version: str) -> tuple[int, int]:
    candidates_sql = '''
        SELECT
            source_item.id AS from_id,
            target_item.id AS to_id,
            resolution.recording_msid,
            resolution.chosen_recording_mbid,
            resolution.winner_shard_observation_count,
            resolution.total_shard_observation_count,
            resolution.candidate_count,
            resolution.winner_share
        FROM mlcore_listenbrainz_msid_mbid_conflict_resolution resolution
        JOIN mlcore_canonical_item source_item
          ON source_item.canonical_key = 'recording_msid:' || resolution.recording_msid::text
        JOIN mlcore_canonical_item target_item
          ON target_item.canonical_key = 'recording_mbid:' || resolution.chosen_recording_mbid::text
        WHERE resolution.source_version = %s
          AND resolution.policy_version = %s
          AND resolution.status = 'active'
    '''
    with transaction.atomic(), connection.cursor() as cursor:
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
            [CONFLICT_RESOLVER_SOURCE_ID, source_version, source_version, policy_version],
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
                candidate.winner_share,
                %s,
                %s,
                'active',
                jsonb_build_object(
                    'recording_msid', candidate.recording_msid,
                    'recording_mbid', candidate.chosen_recording_mbid,
                    'policy_version', %s,
                    'winner_shard_observation_count', candidate.winner_shard_observation_count,
                    'total_shard_observation_count', candidate.total_shard_observation_count,
                    'candidate_count', candidate.candidate_count,
                    'winner_share', candidate.winner_share,
                    'evidence_basis', 'shard_observation_count'
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
                source = EXCLUDED.source,
                source_version = EXCLUDED.source_version,
                evidence = CASE
                    WHEN mlcore_canonical_item_redirect.to_canonical_item_id = EXCLUDED.to_canonical_item_id
                    THEN EXCLUDED.evidence
                    ELSE mlcore_canonical_item_redirect.evidence || jsonb_build_object(
                        'conflicting_target_id', EXCLUDED.to_canonical_item_id,
                        'conflicting_source', EXCLUDED.source
                    )
                END,
                updated_at = NOW()
            ''',
            [
                CONFLICT_RESOLVER_SOURCE_ID,
                source_version,
                policy_version,
                source_version,
                policy_version,
            ],
        )
        cursor.execute(
            '''
            SELECT COUNT(*) FILTER (WHERE status = 'active'),
                   COUNT(*) FILTER (WHERE status = 'conflict')
            FROM mlcore_canonical_item_redirect
            WHERE source = %s AND source_version = %s
            ''',
            [CONFLICT_RESOLVER_SOURCE_ID, source_version],
        )
        redirect_count, redirect_conflict_count = (int(value) for value in cursor.fetchone())
    return redirect_count, redirect_conflict_count


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
