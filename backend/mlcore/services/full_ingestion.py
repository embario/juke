from __future__ import annotations

import csv
import hashlib
import json
import multiprocessing
import shutil
import tarfile
import uuid
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, ThreadPoolExecutor, wait
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from django.conf import settings
from django.db import IntegrityError, close_old_connections, connection, transaction
from django.utils import timezone

from mlcore.ingestion.listenbrainz import (
    configured_dump_path,
    infer_source_version_from_path,
    iter_listenbrainz_json_payloads,
    parse_listenbrainz_payload,
)
from mlcore.models import SourceIngestionRun
from mlcore.models import FullIngestionLease
from mlcore.services.listenbrainz_shards import (
    configured_listenbrainz_shard_root,
    listenbrainz_shard_relative_path,
)

FULL_INGESTION_MANIFEST_VERSION = 2
FULL_INGESTION_STATUS_PLANNED = 'planned'
FULL_INGESTION_STATUS_RUNNING = 'running'
FULL_INGESTION_STATUS_SUCCEEDED = 'succeeded'
FULL_INGESTION_STATUS_FAILED = 'failed'
FULL_INGESTION_STAGE_PLANNED = 'planned'
FULL_INGESTION_STAGE_PARTITION = 'partition'
FULL_INGESTION_STAGE_COPY = 'copy'
FULL_INGESTION_STAGE_MERGE = 'merge'
FULL_INGESTION_STAGE_COMPLETE = 'complete'
FULL_INGESTION_STAGE_PIPELINE = 'pipeline'
PROGRESS_COUNTER_FIELDS = (
    'artifacts_discovered',
    'artifacts_partitioned',
    'input_bytes_partitioned',
    'rows_parsed',
    'rows_staged',
    'session_rows_loaded',
    'rows_merged',
    'rows_deduplicated',
    'rows_resolved',
    'rows_unresolved',
    'rows_malformed',
    'chunks_written',
    'chunks_loaded',
    'partitions_completed',
    'partitions_loaded',
    'partitions_merged',
    'partitions_failed',
)
LISTENBRAINZ_EVENT_LOAD_TABLE = 'mlcore_listenbrainz_event_load'
LISTENBRAINZ_SESSION_LOAD_TABLE = 'mlcore_listenbrainz_session_delta_load'
LISTENBRAINZ_EVENT_LEDGER_TABLE = 'mlcore_listenbrainz_event_ledger'
LISTENBRAINZ_SESSION_TRACK_TABLE = 'mlcore_listenbrainz_session_track'
LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE = 'mlcore_listenbrainz_event_ledger_build'
LISTENBRAINZ_EVENT_LEDGER_BACKUP_TABLE = 'mlcore_listenbrainz_event_ledger_old'
LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE = 'mlcore_listenbrainz_session_track_build'
LISTENBRAINZ_SESSION_TRACK_BACKUP_TABLE = 'mlcore_listenbrainz_session_track_old'
_LISTENBRAINZ_EXTRACT_IDENTITY_SNAPSHOT: ListenBrainzIdentitySnapshot | None = None
_LISTENBRAINZ_EXTRACT_PARTITION_ROOT: str = ''
_LISTENBRAINZ_EXTRACT_RUN_ID: str = ''
_LISTENBRAINZ_EXTRACT_PARTITION_COUNT: int = 0
_LISTENBRAINZ_EXTRACT_CHUNK_TARGET_ROWS: int = 0


class FullIngestionLeaseHeldError(RuntimeError):
    pass


@dataclass(frozen=True)
class FullIngestionPartitionPlan:
    partition_key: str
    index: int
    state: str
    estimated_input_bytes: int
    estimated_shard_count: int
    actual_input_bytes: int = 0
    actual_artifact_count: int = 0


@dataclass(frozen=True)
class FullIngestionPartitionArtifact:
    partition_key: str
    partition_index: int
    source_member_name: str
    relative_path: str
    size_bytes: int
    sha256: str


@dataclass(frozen=True)
class FullIngestionCopyResult:
    partition_key: str
    rows_loaded: int
    session_rows_loaded: int
    chunks_loaded: int
    copy_manifest_path: str


@dataclass(frozen=True)
class FullIngestionMergeResult:
    rows_merged: int
    rows_deduplicated: int
    rows_resolved: int
    rows_unresolved: int
    session_rows_merged: int


@dataclass(frozen=True)
class ListenBrainzMemberChunkResult:
    member_token: str
    counters: dict[str, int]
    chunk_manifests_by_partition: dict[str, list[dict[str, int | str]]]


@dataclass(frozen=True)
class FullIngestionPlan:
    run_id: str
    provider: str
    source_version: str
    archive_path: str
    archive_size_bytes: int
    materialized_manifest_path: str
    scratch_root: str
    run_root: str
    partition_root: str
    log_root: str
    manifest_path: str
    metrics_path: str
    partition_count: int
    partition_workers: int
    load_workers: int
    merge_workers: int
    total_estimated_uncompressed_bytes: int
    source_ingestion_run_id: str
    stage: str
    status: str
    created_at: str
    updated_at: str
    counters: dict[str, int]
    partitions: list[FullIngestionPartitionPlan]


class FullDatasetIngestionProvider(Protocol):
    provider: str

    def configured_archive_path(self) -> str | None:
        ...

    def infer_source_version(self, archive_path: str | Path) -> str:
        ...

    def discover_materialized_manifest(self, source_version: str) -> Path | None:
        ...

    def extract_archive(self, plan: FullIngestionPlan) -> FullIngestionPlan:
        ...

    def ensure_load_tables(self) -> None:
        ...

    def load_partition_to_load_tables(
        self,
        plan: FullIngestionPlan,
        partition: FullIngestionPartitionPlan,
    ) -> FullIngestionCopyResult:
        ...

    def finalize_into_final_tables(
        self,
        plan: FullIngestionPlan,
        *,
        source_ingestion_run: SourceIngestionRun,
    ) -> FullIngestionMergeResult:
        ...


@dataclass(frozen=True)
class ListenBrainzFullIngestionProvider:
    provider: str = 'listenbrainz'

    def configured_archive_path(self) -> str | None:
        return configured_dump_path('full')

    def infer_source_version(self, archive_path: str | Path) -> str:
        return infer_source_version_from_path(archive_path)

    def discover_materialized_manifest(self, source_version: str) -> Path | None:
        resolved_shard_root = configured_listenbrainz_shard_root()
        manifest_path = resolved_shard_root / source_version / 'manifest.json'
        return manifest_path if manifest_path.exists() else None

    def extract_archive(self, plan: FullIngestionPlan) -> FullIngestionPlan:
        return extract_listenbrainz_archive(plan)

    def ensure_load_tables(self) -> None:
        ensure_listenbrainz_load_tables()

    def load_partition_to_load_tables(
        self,
        plan: FullIngestionPlan,
        partition: FullIngestionPartitionPlan,
    ) -> FullIngestionCopyResult:
        return load_listenbrainz_partition_to_load_tables(plan, partition)

    def finalize_into_final_tables(
        self,
        plan: FullIngestionPlan,
        *,
        source_ingestion_run: SourceIngestionRun,
    ) -> FullIngestionMergeResult:
        return finalize_listenbrainz_full_ingestion(
            plan,
            source_ingestion_run=source_ingestion_run,
        )


LISTENBRAINZ_FULL_INGESTION_PROVIDER = ListenBrainzFullIngestionProvider()


def get_full_ingestion_provider(provider: str) -> FullDatasetIngestionProvider:
    normalized = str(provider or '').strip().casefold()
    if normalized == 'listenbrainz':
        return LISTENBRAINZ_FULL_INGESTION_PROVIDER
    raise ValueError(f"Unsupported full-ingestion provider '{provider}'")


def configured_full_ingestion_scratch_root() -> Path:
    return Path(
        getattr(settings, 'MLCORE_FULL_INGESTION_SCRATCH_ROOT', '/srv/data/juke/full-ingestion')
    )


def configured_full_ingestion_partition_count() -> int:
    return max(1, int(getattr(settings, 'MLCORE_FULL_INGESTION_PARTITION_COUNT', 128)))


def configured_full_ingestion_partition_workers() -> int:
    return max(1, int(getattr(settings, 'MLCORE_FULL_INGESTION_PARTITION_WORKERS', 16)))


def configured_full_ingestion_load_workers() -> int:
    return max(1, int(getattr(settings, 'MLCORE_FULL_INGESTION_LOAD_WORKERS', 4)))


def configured_full_ingestion_merge_workers() -> int:
    return max(1, int(getattr(settings, 'MLCORE_FULL_INGESTION_MERGE_WORKERS', 4)))


def configured_full_ingestion_target_chunk_rows() -> int:
    return max(1, int(getattr(settings, 'MLCORE_FULL_INGESTION_TARGET_CHUNK_ROWS', 250000)))


def configured_full_ingestion_metrics_path() -> Path | None:
    value = str(getattr(settings, 'MLCORE_FULL_INGESTION_TEXTFILE_METRICS_PATH', '') or '').strip()
    if not value:
        return None
    return Path(value)


def configured_full_ingestion_lease_timeout_seconds() -> int:
    return max(60, int(getattr(settings, 'MLCORE_FULL_INGESTION_LEASE_TIMEOUT_SECONDS', 60 * 30)))


def full_ingestion_lease_is_stale(
    lease: FullIngestionLease,
    *,
    now: datetime | None = None,
) -> bool:
    reference = now or timezone.now()
    return (reference - lease.heartbeat_at).total_seconds() > configured_full_ingestion_lease_timeout_seconds()


def get_active_full_ingestion_lease(provider: str) -> FullIngestionLease | None:
    lease = FullIngestionLease.objects.filter(provider=provider).first()
    if lease is None:
        return None
    if lease.status != FULL_INGESTION_STATUS_RUNNING:
        return None
    if full_ingestion_lease_is_stale(lease):
        return None
    return lease


def full_ingestion_conflict_metadata(provider: str) -> dict[str, str] | None:
    lease = get_active_full_ingestion_lease(provider)
    if lease is None:
        return None
    return {
        'reason': 'full_ingestion_active',
        'lease_run_id': lease.holder_run_id,
        'lease_provider': lease.provider,
        'lease_source_version': lease.source_version,
        'lease_heartbeat_at': lease.heartbeat_at.isoformat(),
    }


def acquire_full_ingestion_lease(
    *,
    provider: str,
    run_id: str,
    source_version: str,
    stage: str,
    metadata: dict[str, Any] | None = None,
) -> FullIngestionLease:
    now = timezone.now()
    payload = dict(metadata or {})
    payload.update(
        {
            'run_id': run_id,
            'source_version': source_version,
            'stage': stage,
        }
    )
    with transaction.atomic():
        lease = FullIngestionLease.objects.select_for_update().filter(provider=provider).first()
        if lease is None:
            try:
                return FullIngestionLease.objects.create(
                    provider=provider,
                    holder_run_id=run_id,
                    source_version=source_version,
                    status=FULL_INGESTION_STATUS_RUNNING,
                    metadata=payload,
                )
            except IntegrityError:
                lease = FullIngestionLease.objects.select_for_update().get(provider=provider)

        if (
            lease.status == FULL_INGESTION_STATUS_RUNNING
            and lease.holder_run_id
            and lease.holder_run_id != run_id
            and not full_ingestion_lease_is_stale(lease, now=now)
        ):
            raise FullIngestionLeaseHeldError(
                f"Provider '{provider}' is already locked by full-ingestion run {lease.holder_run_id}."
            )

        lease.holder_type = 'full_ingestion'
        lease.holder_run_id = run_id
        lease.source_version = source_version
        lease.status = FULL_INGESTION_STATUS_RUNNING
        lease.metadata = {
            **lease.metadata,
            **payload,
        }
        lease.released_at = None
        lease.save(
            update_fields=[
                'holder_type',
                'holder_run_id',
                'source_version',
                'status',
                'metadata',
                'released_at',
                'heartbeat_at',
            ]
        )
        return lease


def touch_full_ingestion_lease(
    *,
    provider: str,
    run_id: str,
    stage: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    payload = dict(metadata or {})
    payload['stage'] = stage
    lease = FullIngestionLease.objects.filter(
        provider=provider,
        holder_run_id=run_id,
    ).first()
    if lease is None:
        return

    lease.status = FULL_INGESTION_STATUS_RUNNING
    lease.metadata = {
        **lease.metadata,
        **payload,
    }
    lease.released_at = None
    lease.save(update_fields=['status', 'metadata', 'released_at', 'heartbeat_at'])


def release_full_ingestion_lease(
    *,
    provider: str,
    run_id: str,
    status: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    payload = dict(metadata or {})
    payload['released_status'] = status
    FullIngestionLease.objects.filter(
        provider=provider,
        holder_run_id=run_id,
    ).update(
        status=status,
        metadata=payload,
        heartbeat_at=timezone.now(),
        released_at=timezone.now(),
    )


def full_ingestion_run_root(
    *,
    provider: str,
    source_version: str,
    scratch_root: str | Path | None = None,
) -> Path:
    resolved_scratch_root = Path(scratch_root) if scratch_root is not None else configured_full_ingestion_scratch_root()
    return resolved_scratch_root / str(provider).strip() / str(source_version).strip()


def full_ingestion_manifest_path(
    *,
    provider: str,
    source_version: str,
    scratch_root: str | Path | None = None,
) -> Path:
    return full_ingestion_run_root(
        provider=provider,
        source_version=source_version,
        scratch_root=scratch_root,
    ) / 'full-ingestion-manifest.json'


def full_ingestion_partition_state_counts(
    plan: FullIngestionPlan,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for partition in plan.partitions:
        counts[partition.state] = counts.get(partition.state, 0) + 1
    return counts


def partition_index_for_path(relative_path: str, *, partition_count: int) -> int:
    digest = hashlib.sha256(relative_path.encode('utf-8')).hexdigest()
    return int(digest[:16], 16) % partition_count


def build_full_ingestion_partition_estimates(
    materialized_manifest_path: str | Path,
    *,
    partition_count: int,
) -> tuple[int, list[dict[str, int]]]:
    payload = json.loads(Path(materialized_manifest_path).read_text(encoding='utf-8'))
    partitions = [{'estimated_input_bytes': 0, 'estimated_shard_count': 0} for _ in range(partition_count)]
    total_uncompressed_bytes = int(payload.get('total_uncompressed_bytes') or 0)

    for shard in payload.get('shards', []):
        relative_path = str(shard['relative_path'])
        shard_size_bytes = int(shard.get('size_bytes') or 0)
        partition_index = partition_index_for_path(relative_path, partition_count=partition_count)
        partitions[partition_index]['estimated_input_bytes'] += shard_size_bytes
        partitions[partition_index]['estimated_shard_count'] += 1

    return total_uncompressed_bytes, partitions


def build_full_ingestion_plan(
    provider: str,
    archive_path: str | Path,
    *,
    source_version: str | None = None,
    scratch_root: str | Path | None = None,
    partition_count: int | None = None,
    partition_workers: int | None = None,
    load_workers: int | None = None,
    merge_workers: int | None = None,
    metrics_path: str | Path | None = None,
    materialized_manifest_path: str | Path | None = None,
) -> FullIngestionPlan:
    ingestion_provider = get_full_ingestion_provider(provider)
    resolved_archive_path = Path(archive_path)
    if not resolved_archive_path.exists():
        raise FileNotFoundError(f'{ingestion_provider.provider} archive not found: {resolved_archive_path}')

    resolved_source_version = source_version or ingestion_provider.infer_source_version(resolved_archive_path)
    resolved_scratch_root = Path(scratch_root) if scratch_root is not None else configured_full_ingestion_scratch_root()
    resolved_partition_count = max(1, int(partition_count or configured_full_ingestion_partition_count()))
    resolved_partition_workers = max(
        1, int(partition_workers or configured_full_ingestion_partition_workers())
    )
    resolved_load_workers = max(1, int(load_workers or configured_full_ingestion_load_workers()))
    resolved_merge_workers = max(1, int(merge_workers or configured_full_ingestion_merge_workers()))
    resolved_metrics_path = (
        Path(metrics_path)
        if metrics_path is not None
        else configured_full_ingestion_metrics_path()
    )

    discovered_materialized_manifest = (
        Path(materialized_manifest_path)
        if materialized_manifest_path is not None
        else ingestion_provider.discover_materialized_manifest(resolved_source_version)
    )
    resolved_run_root = resolved_scratch_root / ingestion_provider.provider / resolved_source_version
    manifest_path = resolved_run_root / 'full-ingestion-manifest.json'
    now = datetime.now(tz=UTC).isoformat()
    counters = {field: 0 for field in PROGRESS_COUNTER_FIELDS}
    total_estimated_uncompressed_bytes = 0
    partition_estimates = [{'estimated_input_bytes': 0, 'estimated_shard_count': 0} for _ in range(resolved_partition_count)]

    if discovered_materialized_manifest is not None and discovered_materialized_manifest.exists():
        total_estimated_uncompressed_bytes, partition_estimates = build_full_ingestion_partition_estimates(
            discovered_materialized_manifest,
            partition_count=resolved_partition_count,
        )

    partitions = [
        FullIngestionPartitionPlan(
            partition_key=f'p{index:03d}',
            index=index,
            state='pending',
            estimated_input_bytes=partition_estimates[index]['estimated_input_bytes'],
            estimated_shard_count=partition_estimates[index]['estimated_shard_count'],
        )
        for index in range(resolved_partition_count)
    ]

    return FullIngestionPlan(
        run_id=str(uuid.uuid4()),
        provider=ingestion_provider.provider,
        source_version=resolved_source_version,
        archive_path=str(resolved_archive_path),
        archive_size_bytes=resolved_archive_path.stat().st_size,
        materialized_manifest_path=str(discovered_materialized_manifest or ''),
        scratch_root=str(resolved_scratch_root),
        run_root=str(resolved_run_root),
        partition_root=str(resolved_run_root / 'partitions'),
        log_root=str(resolved_run_root / 'logs'),
        manifest_path=str(manifest_path),
        metrics_path=str(resolved_metrics_path or ''),
        partition_count=resolved_partition_count,
        partition_workers=resolved_partition_workers,
        load_workers=resolved_load_workers,
        merge_workers=resolved_merge_workers,
        total_estimated_uncompressed_bytes=total_estimated_uncompressed_bytes,
        source_ingestion_run_id='',
        stage=FULL_INGESTION_STAGE_PLANNED,
        status=FULL_INGESTION_STATUS_PLANNED,
        created_at=now,
        updated_at=now,
        counters=counters,
        partitions=partitions,
    )


def full_ingestion_plan_to_dict(plan: FullIngestionPlan) -> dict[str, Any]:
    return {
        'manifest_version': FULL_INGESTION_MANIFEST_VERSION,
        'run_id': plan.run_id,
        'provider': plan.provider,
        'source_version': plan.source_version,
        'archive_path': plan.archive_path,
        'archive_size_bytes': plan.archive_size_bytes,
        'materialized_manifest_path': plan.materialized_manifest_path,
        'scratch_root': plan.scratch_root,
        'run_root': plan.run_root,
        'partition_root': plan.partition_root,
        'log_root': plan.log_root,
        'manifest_path': plan.manifest_path,
        'metrics_path': plan.metrics_path,
        'partition_count': plan.partition_count,
        'worker_config': {
            'partition_workers': plan.partition_workers,
            'load_workers': plan.load_workers,
            'merge_workers': plan.merge_workers,
        },
        'total_estimated_uncompressed_bytes': plan.total_estimated_uncompressed_bytes,
        'source_ingestion_run_id': plan.source_ingestion_run_id,
        'stage': plan.stage,
        'status': plan.status,
        'created_at': plan.created_at,
        'updated_at': plan.updated_at,
        'counters': dict(plan.counters),
        'partitions': [
            {
                'partition_key': partition.partition_key,
                'index': partition.index,
                'state': partition.state,
                'estimated_input_bytes': partition.estimated_input_bytes,
                'estimated_shard_count': partition.estimated_shard_count,
                'actual_input_bytes': partition.actual_input_bytes,
                'actual_artifact_count': partition.actual_artifact_count,
            }
            for partition in plan.partitions
        ],
    }


def load_full_ingestion_plan(manifest_path: str | Path) -> FullIngestionPlan:
    payload = json.loads(Path(manifest_path).read_text(encoding='utf-8'))
    counters = {field: int((payload.get('counters') or {}).get(field) or 0) for field in PROGRESS_COUNTER_FIELDS}
    partitions = [
        FullIngestionPartitionPlan(
            partition_key=str(partition['partition_key']),
            index=int(partition['index']),
            state=str(partition['state']),
            estimated_input_bytes=int(partition.get('estimated_input_bytes') or 0),
            estimated_shard_count=int(partition.get('estimated_shard_count') or 0),
            actual_input_bytes=int(partition.get('actual_input_bytes') or 0),
            actual_artifact_count=int(partition.get('actual_artifact_count') or 0),
        )
        for partition in payload.get('partitions', [])
    ]
    worker_config = dict(payload.get('worker_config') or {})
    return FullIngestionPlan(
        run_id=str(payload['run_id']),
        provider=str(payload['provider']),
        source_version=str(payload['source_version']),
        archive_path=str(payload['archive_path']),
        archive_size_bytes=int(payload.get('archive_size_bytes') or 0),
        materialized_manifest_path=str(payload.get('materialized_manifest_path') or ''),
        scratch_root=str(payload['scratch_root']),
        run_root=str(payload['run_root']),
        partition_root=str(payload['partition_root']),
        log_root=str(payload['log_root']),
        manifest_path=str(payload['manifest_path']),
        metrics_path=str(payload.get('metrics_path') or ''),
        partition_count=int(payload['partition_count']),
        partition_workers=int(worker_config.get('partition_workers') or 0),
        load_workers=int(worker_config.get('load_workers') or 0),
        merge_workers=int(worker_config.get('merge_workers') or 0),
        total_estimated_uncompressed_bytes=int(payload.get('total_estimated_uncompressed_bytes') or 0),
        source_ingestion_run_id=str(payload.get('source_ingestion_run_id') or ''),
        stage=str(payload['stage']),
        status=str(payload['status']),
        created_at=str(payload['created_at']),
        updated_at=str(payload['updated_at']),
        counters=counters,
        partitions=partitions,
    )


def initialize_full_ingestion_plan(plan: FullIngestionPlan, *, force: bool = False) -> FullIngestionPlan:
    run_root = Path(plan.run_root)
    if run_root.exists() and not force:
        raise FileExistsError(
            f'Full-ingestion run root already exists at {run_root}; rerun with force=True to replace it or resume.'
        )
    if force and run_root.exists():
        shutil.rmtree(run_root)

    Path(plan.partition_root).mkdir(parents=True, exist_ok=True)
    Path(plan.log_root).mkdir(parents=True, exist_ok=True)
    write_full_ingestion_plan(plan)
    write_full_ingestion_metrics(plan)
    return plan


def execute_full_ingestion_partition_stage(
    plan: FullIngestionPlan,
    *,
    force: bool = False,
) -> FullIngestionPlan:
    if any(partition.state != 'pending' for partition in plan.partitions):
        if not force and all(partition.state == 'partitioned' for partition in plan.partitions):
            return plan
        if not force:
            raise ValueError(
                'Partition stage has already started for this full-ingestion plan; rerun with force=True to replace it.'
            )

    partition_root = Path(plan.partition_root)
    if force and partition_root.exists():
        shutil.rmtree(partition_root)
    partition_root.mkdir(parents=True, exist_ok=True)

    running_plan = replace(
        plan,
        stage=FULL_INGESTION_STAGE_PARTITION,
        status=FULL_INGESTION_STATUS_RUNNING,
        updated_at=datetime.now(tz=UTC).isoformat(),
        counters={
            **plan.counters,
            'artifacts_discovered': 0,
            'artifacts_partitioned': 0,
            'input_bytes_partitioned': 0,
            'rows_parsed': 0,
            'rows_resolved': 0,
            'rows_unresolved': 0,
            'rows_malformed': 0,
            'chunks_written': 0,
            'partitions_completed': 0,
            'partitions_failed': 0,
        },
    )
    _persist_full_ingestion_state(running_plan)

    provider = get_full_ingestion_provider(running_plan.provider)
    try:
        return provider.extract_archive(running_plan)
    except Exception:
        failed_plan = replace(
            running_plan,
            status=FULL_INGESTION_STATUS_FAILED,
            updated_at=datetime.now(tz=UTC).isoformat(),
            counters={
                **running_plan.counters,
                'partitions_failed': running_plan.partition_count,
            },
        )
        _persist_full_ingestion_state(failed_plan)
        raise


def full_ingestion_partition_manifest_path(
    plan: FullIngestionPlan,
    *,
    partition_key: str,
) -> Path:
    return Path(plan.partition_root) / partition_key / 'manifest.json'


def write_full_ingestion_partition_manifest(
    plan: FullIngestionPlan,
    *,
    partition: FullIngestionPartitionPlan,
    chunks: list[dict[str, int | str]],
) -> Path:
    path = full_ingestion_partition_manifest_path(plan, partition_key=partition.partition_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'run_id': plan.run_id,
        'provider': plan.provider,
        'source_version': plan.source_version,
        'partition_key': partition.partition_key,
        'partition_index': partition.index,
        'stage': FULL_INGESTION_STAGE_PARTITION,
        'event_chunk_count': len(chunks),
        'total_input_bytes': sum(int(chunk.get('size_bytes') or 0) for chunk in chunks),
        'event_chunks': list(chunks),
    }
    temp_path = path.with_name(path.name + '.tmp')
    temp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    temp_path.replace(path)
    return path


def execute_full_ingestion_copy_stage(
    plan: FullIngestionPlan,
    *,
    force: bool = False,
) -> FullIngestionPlan:
    if any(partition.state not in ('partitioned', 'loaded') for partition in plan.partitions):
        raise ValueError('Copy stage requires all partitions to be extracted first.')

    if all(partition.state == 'loaded' for partition in plan.partitions) and not force:
        return plan

    provider = get_full_ingestion_provider(plan.provider)
    provider.ensure_load_tables()

    running_plan = replace(
        plan,
        stage=FULL_INGESTION_STAGE_COPY,
        status=FULL_INGESTION_STATUS_RUNNING,
        updated_at=datetime.now(tz=UTC).isoformat(),
        counters={
            **plan.counters,
            'rows_staged': 0 if force else int(plan.counters.get('rows_staged') or 0),
            'session_rows_loaded': 0 if force else int(plan.counters.get('session_rows_loaded') or 0),
            'chunks_loaded': 0 if force else int(plan.counters.get('chunks_loaded') or 0),
            'partitions_loaded': 0 if force else int(plan.counters.get('partitions_loaded') or 0),
        },
    )
    _persist_full_ingestion_state(running_plan)

    counters = dict(running_plan.counters)
    finalized_partitions: list[FullIngestionPartitionPlan] = list(running_plan.partitions)
    partition_index_by_key = {partition.partition_key: index for index, partition in enumerate(finalized_partitions)}
    counters['partitions_loaded'] = 0 if force else sum(1 for partition in finalized_partitions if partition.state == 'loaded')
    pending_partition_keys = [
        partition.partition_key
        for partition in finalized_partitions
        if force or partition.state != 'loaded'
    ]

    def _load_partition_lane(partition_key: str) -> tuple[str, FullIngestionCopyResult]:
        close_old_connections()
        try:
            partition = finalized_partitions[partition_index_by_key[partition_key]]
            result = provider.load_partition_to_load_tables(running_plan, partition)
            return partition_key, result
        finally:
            close_old_connections()

    try:
        future_to_partition: dict[Any, str] = {}
        partition_iter = iter(pending_partition_keys)
        with ThreadPoolExecutor(max_workers=max(1, plan.load_workers)) as executor:
            for _ in range(min(max(1, plan.load_workers), len(pending_partition_keys))):
                partition_key = next(partition_iter, None)
                if partition_key is None:
                    break
                future = executor.submit(_load_partition_lane, partition_key)
                future_to_partition[future] = partition_key

            while future_to_partition:
                done, _ = wait(future_to_partition.keys(), return_when=FIRST_COMPLETED)
                for future in done:
                    partition_key = future_to_partition.pop(future)
                    try:
                        _, result = future.result()
                    except Exception:
                        index = partition_index_by_key[partition_key]
                        finalized_partitions[index] = replace(finalized_partitions[index], state='failed')
                        raise
                    index = partition_index_by_key[partition_key]
                    partition = finalized_partitions[index]
                    counters['rows_staged'] = int(counters.get('rows_staged') or 0) + result.rows_loaded
                    counters['session_rows_loaded'] = (
                        int(counters.get('session_rows_loaded') or 0) + result.session_rows_loaded
                    )
                    counters['chunks_loaded'] = int(counters.get('chunks_loaded') or 0) + result.chunks_loaded
                    counters['partitions_loaded'] = int(counters.get('partitions_loaded') or 0) + 1
                    finalized_partitions[index] = replace(partition, state='loaded')
                    write_full_ingestion_copy_manifest(
                        running_plan,
                        partition=finalized_partitions[index],
                        result=result,
                    )
                    running_plan = replace(
                        running_plan,
                        updated_at=datetime.now(tz=UTC).isoformat(),
                        counters=dict(counters),
                        partitions=list(finalized_partitions),
                    )
                    _persist_full_ingestion_state(running_plan)

                    next_partition_key = next(partition_iter, None)
                    if next_partition_key is not None:
                        next_future = executor.submit(_load_partition_lane, next_partition_key)
                        future_to_partition[next_future] = next_partition_key
    except Exception:
        failed_plan = replace(
            running_plan,
            status=FULL_INGESTION_STATUS_FAILED,
            updated_at=datetime.now(tz=UTC).isoformat(),
            counters={
                **counters,
                'partitions_failed': sum(
                    1 for partition in finalized_partitions if partition.state == 'failed'
                ),
            },
            partitions=list(finalized_partitions),
        )
        _persist_full_ingestion_state(failed_plan)
        raise

    completed_plan = replace(
        running_plan,
        updated_at=datetime.now(tz=UTC).isoformat(),
        counters=dict(counters),
        partitions=list(finalized_partitions),
    )
    _persist_full_ingestion_state(completed_plan)
    return completed_plan


def execute_full_ingestion_merge_stage(
    plan: FullIngestionPlan,
    *,
    force: bool = False,
) -> FullIngestionPlan:
    if any(partition.state not in ('loaded', 'merged') for partition in plan.partitions):
        raise ValueError('Merge stage requires all partitions to be loaded into lean load tables first.')

    if all(partition.state == 'merged' for partition in plan.partitions) and not force:
        return plan

    provider = get_full_ingestion_provider(plan.provider)
    source_ingestion_run, source_ingestion_run_id = ensure_full_ingestion_source_run(plan)
    running_plan = replace(
        plan,
        stage=FULL_INGESTION_STAGE_MERGE,
        status=FULL_INGESTION_STATUS_RUNNING,
        source_ingestion_run_id=str(source_ingestion_run_id),
        updated_at=datetime.now(tz=UTC).isoformat(),
        counters={
            **plan.counters,
            'rows_merged': 0 if force else int(plan.counters.get('rows_merged') or 0),
            'rows_deduplicated': 0 if force else int(plan.counters.get('rows_deduplicated') or 0),
            'partitions_merged': 0 if force else int(plan.counters.get('partitions_merged') or 0),
        },
    )
    _persist_full_ingestion_state(running_plan)
    try:
        result = provider.finalize_into_final_tables(
            running_plan,
            source_ingestion_run=source_ingestion_run,
        )
    except Exception as exc:
        failed_plan = replace(
            running_plan,
            status=FULL_INGESTION_STATUS_FAILED,
            updated_at=datetime.now(tz=UTC).isoformat(),
            counters={
                **running_plan.counters,
                'partitions_failed': running_plan.partition_count,
            },
            partitions=[replace(partition, state='failed') for partition in running_plan.partitions],
        )
        _persist_full_ingestion_state(failed_plan)
        _mark_full_ingestion_source_run_failed(source_ingestion_run, failed_plan, error=str(exc))
        raise

    completed_plan = replace(
        running_plan,
        stage=FULL_INGESTION_STAGE_COMPLETE,
        status=FULL_INGESTION_STATUS_SUCCEEDED,
        updated_at=datetime.now(tz=UTC).isoformat(),
        counters={
            **running_plan.counters,
            'rows_merged': result.rows_merged,
            'rows_deduplicated': result.rows_deduplicated,
            'rows_resolved': result.rows_resolved,
            'rows_unresolved': result.rows_unresolved,
            'partitions_merged': running_plan.partition_count,
            'partitions_failed': 0,
        },
        partitions=[replace(partition, state='merged') for partition in running_plan.partitions],
    )
    write_full_ingestion_merge_manifest(
        completed_plan,
        partition=replace(completed_plan.partitions[0], partition_key='finalize', index=-1),
        result=result,
    )
    _persist_full_ingestion_state(completed_plan)
    finalize_full_ingestion_source_run(source_ingestion_run, completed_plan)
    return completed_plan


def execute_full_ingestion_pipeline(
    plan: FullIngestionPlan,
    *,
    force: bool = False,
) -> FullIngestionPlan:
    if plan.stage == FULL_INGESTION_STAGE_PLANNED:
        plan = execute_full_ingestion_partition_stage(plan, force=force)
    if any(partition.state == 'pending' for partition in plan.partitions):
        raise ValueError('Pipeline execution requires all partitions to be extracted first.')
    if any(partition.state == 'partitioned' for partition in plan.partitions):
        plan = execute_full_ingestion_copy_stage(plan, force=force)
    if any(partition.state == 'loaded' for partition in plan.partitions):
        plan = execute_full_ingestion_merge_stage(plan, force=force)
    return plan


def full_ingestion_copy_manifest_path(
    plan: FullIngestionPlan,
    *,
    partition_key: str,
) -> Path:
    return Path(plan.partition_root) / partition_key / 'copy-manifest.json'


def write_full_ingestion_copy_manifest(
    plan: FullIngestionPlan,
    *,
    partition: FullIngestionPartitionPlan,
    result: FullIngestionCopyResult,
) -> Path:
    path = full_ingestion_copy_manifest_path(plan, partition_key=partition.partition_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'run_id': plan.run_id,
        'provider': plan.provider,
        'source_version': plan.source_version,
        'partition_key': partition.partition_key,
        'partition_index': partition.index,
        'stage': FULL_INGESTION_STAGE_COPY,
        'rows_loaded': result.rows_loaded,
        'session_rows_loaded': result.session_rows_loaded,
        'chunks_loaded': result.chunks_loaded,
        'copy_manifest_path': result.copy_manifest_path,
    }
    temp_path = path.with_name(path.name + '.tmp')
    temp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    temp_path.replace(path)
    return path


def full_ingestion_merge_manifest_path(
    plan: FullIngestionPlan,
    *,
    partition_key: str,
) -> Path:
    return Path(plan.partition_root) / partition_key / 'merge-manifest.json'


def write_full_ingestion_merge_manifest(
    plan: FullIngestionPlan,
    *,
    partition: FullIngestionPartitionPlan,
    result: FullIngestionMergeResult,
) -> Path:
    path = full_ingestion_merge_manifest_path(plan, partition_key=partition.partition_key)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        'run_id': plan.run_id,
        'provider': plan.provider,
        'source_version': plan.source_version,
        'partition_key': partition.partition_key,
        'partition_index': partition.index,
        'stage': FULL_INGESTION_STAGE_MERGE,
        'rows_merged': result.rows_merged,
        'rows_deduplicated': result.rows_deduplicated,
        'rows_resolved': result.rows_resolved,
        'rows_unresolved': result.rows_unresolved,
        'session_rows_merged': result.session_rows_merged,
    }
    temp_path = path.with_name(path.name + '.tmp')
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    temp_path.replace(path)
    return path


def _persist_full_ingestion_state(plan: FullIngestionPlan) -> None:
    write_full_ingestion_plan(plan)
    write_full_ingestion_metrics(plan)
    touch_full_ingestion_lease(
        provider=plan.provider,
        run_id=plan.run_id,
        stage=plan.stage,
        metadata={
            'source_version': plan.source_version,
            'manifest_path': plan.manifest_path,
            'status': plan.status,
        },
    )


def write_full_ingestion_plan(plan: FullIngestionPlan) -> Path:
    path = Path(plan.manifest_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + '.tmp')
    temp_path.write_text(
        json.dumps(full_ingestion_plan_to_dict(plan), indent=2, sort_keys=True) + '\n',
        encoding='utf-8',
    )
    temp_path.replace(path)
    return path


def write_full_ingestion_metrics(plan: FullIngestionPlan) -> Path | None:
    if not plan.metrics_path:
        return None

    path = Path(plan.metrics_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(path.name + '.tmp')
    partition_states: dict[str, int] = {}
    for partition in plan.partitions:
        partition_states[partition.state] = partition_states.get(partition.state, 0) + 1

    def _escape_label(value: str) -> str:
        return value.replace('\\', '\\\\').replace('"', '\\"')

    created_at = datetime.fromisoformat(plan.created_at)
    updated_at = datetime.fromisoformat(plan.updated_at)
    elapsed_reference = (
        datetime.now(tz=UTC)
        if plan.status in (FULL_INGESTION_STATUS_PLANNED, FULL_INGESTION_STATUS_RUNNING)
        else updated_at
    )
    elapsed_seconds = max(0.0, (elapsed_reference - created_at).total_seconds())

    lines = [
        '# HELP mlcore_full_ingestion_active Whether a full dataset ingestion run is currently active.',
        '# TYPE mlcore_full_ingestion_active gauge',
        (
            'mlcore_full_ingestion_active{'
            f'provider="{_escape_label(plan.provider)}",'
            f'run_id="{_escape_label(plan.run_id)}"'
            '} '
            f'{1 if plan.status in (FULL_INGESTION_STATUS_PLANNED, FULL_INGESTION_STATUS_RUNNING) else 0}'
        ),
        '# HELP mlcore_full_ingestion_info Metadata for the active full-ingestion plan.',
        '# TYPE mlcore_full_ingestion_info gauge',
        (
            'mlcore_full_ingestion_info{'
            f'provider="{_escape_label(plan.provider)}",'
            f'source_version="{_escape_label(plan.source_version)}",'
            f'run_id="{_escape_label(plan.run_id)}",'
            f'status="{_escape_label(plan.status)}",'
            f'stage="{_escape_label(plan.stage)}"'
            '} 1'
        ),
        '# HELP mlcore_full_ingestion_partition_count Total planned hash partitions for the full ingestion run.',
        '# TYPE mlcore_full_ingestion_partition_count gauge',
        (
            'mlcore_full_ingestion_partition_count{'
            f'provider="{_escape_label(plan.provider)}",'
            f'run_id="{_escape_label(plan.run_id)}"'
            '} '
            f'{plan.partition_count}'
        ),
        '# HELP mlcore_full_ingestion_partition_state Partitions grouped by current state.',
        '# TYPE mlcore_full_ingestion_partition_state gauge',
    ]
    for state, count in sorted(partition_states.items()):
        lines.append(
            (
                'mlcore_full_ingestion_partition_state{'
                f'provider="{_escape_label(plan.provider)}",'
                f'run_id="{_escape_label(plan.run_id)}",'
                f'state="{_escape_label(state)}"'
                '} '
                f'{count}'
            )
        )

    lines.extend(
        [
            '# HELP mlcore_full_ingestion_archive_size_bytes Source archive size in bytes.',
            '# TYPE mlcore_full_ingestion_archive_size_bytes gauge',
            (
                'mlcore_full_ingestion_archive_size_bytes{'
                f'provider="{_escape_label(plan.provider)}",'
                f'run_id="{_escape_label(plan.run_id)}"'
                '} '
                f'{plan.archive_size_bytes}'
            ),
            '# HELP mlcore_full_ingestion_estimated_uncompressed_bytes Estimated total uncompressed input bytes.',
            '# TYPE mlcore_full_ingestion_estimated_uncompressed_bytes gauge',
            (
                'mlcore_full_ingestion_estimated_uncompressed_bytes{'
                f'provider="{_escape_label(plan.provider)}",'
                f'run_id="{_escape_label(plan.run_id)}"'
                '} '
                f'{plan.total_estimated_uncompressed_bytes}'
            ),
            '# HELP mlcore_full_ingestion_created_at_unixtime Run creation time as unix seconds.',
            '# TYPE mlcore_full_ingestion_created_at_unixtime gauge',
            (
                'mlcore_full_ingestion_created_at_unixtime{'
                f'provider="{_escape_label(plan.provider)}",'
                f'run_id="{_escape_label(plan.run_id)}"'
                '} '
                f'{created_at.timestamp():.3f}'
            ),
            '# HELP mlcore_full_ingestion_updated_at_unixtime Last manifest update time as unix seconds.',
            '# TYPE mlcore_full_ingestion_updated_at_unixtime gauge',
            (
                'mlcore_full_ingestion_updated_at_unixtime{'
                f'provider="{_escape_label(plan.provider)}",'
                f'run_id="{_escape_label(plan.run_id)}"'
                '} '
                f'{updated_at.timestamp():.3f}'
            ),
            '# HELP mlcore_full_ingestion_elapsed_seconds Elapsed wall-clock seconds for the run manifest window.',
            '# TYPE mlcore_full_ingestion_elapsed_seconds gauge',
            (
                'mlcore_full_ingestion_elapsed_seconds{'
                f'provider="{_escape_label(plan.provider)}",'
                f'run_id="{_escape_label(plan.run_id)}"'
                '} '
                f'{elapsed_seconds:.3f}'
            ),
            '# HELP mlcore_full_ingestion_worker_config Configured worker counts by role.',
            '# TYPE mlcore_full_ingestion_worker_config gauge',
            (
                'mlcore_full_ingestion_worker_config{'
                f'provider="{_escape_label(plan.provider)}",'
                f'run_id="{_escape_label(plan.run_id)}",role="partition"'
                '} '
                f'{plan.partition_workers}'
            ),
            (
                'mlcore_full_ingestion_worker_config{'
                f'provider="{_escape_label(plan.provider)}",'
                f'run_id="{_escape_label(plan.run_id)}",role="load"'
                '} '
                f'{plan.load_workers}'
            ),
            (
                'mlcore_full_ingestion_worker_config{'
                f'provider="{_escape_label(plan.provider)}",'
                f'run_id="{_escape_label(plan.run_id)}",role="merge"'
                '} '
                f'{plan.merge_workers}'
            ),
        ]
    )
    for field in PROGRESS_COUNTER_FIELDS:
        metric_name = f'mlcore_full_ingestion_{field}'
        lines.append(f'# HELP {metric_name} Current {field.replace("_", " ")} for the full ingestion run.')
        lines.append(f'# TYPE {metric_name} gauge')
        lines.append(
            (
                f'{metric_name}' + '{'
                f'provider="{_escape_label(plan.provider)}",'
                f'run_id="{_escape_label(plan.run_id)}"'
                '} '
                f'{int(plan.counters.get(field) or 0)}'
            )
        )

    temp_path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    temp_path.replace(path)
    return path


@dataclass(frozen=True)
class ListenBrainzIdentitySnapshot:
    mbid_to_track_id: dict[str, str]
    spotify_to_track_id: dict[str, str]

    def resolve_track_id(self, parsed_payload: Any) -> str:
        if parsed_payload.recording_mbid is not None:
            resolved = self.mbid_to_track_id.get(str(parsed_payload.recording_mbid))
            if resolved:
                return resolved

        spotify_id = str(parsed_payload.track_identifier_candidates.get('spotify_id') or '').strip()
        if spotify_id:
            resolved = self.spotify_to_track_id.get(spotify_id)
            if resolved:
                return resolved

        return ''


class _ListenBrainzPartitionChunkWriter:
    def __init__(
        self,
        *,
        partition_root: Path,
        partition_key: str,
        chunk_target_rows: int,
        file_prefix: str,
    ) -> None:
        self.partition_root = partition_root
        self.partition_key = partition_key
        self.chunk_target_rows = chunk_target_rows
        self.file_prefix = file_prefix
        self.chunk_index = 0
        self.current_rows = 0
        self.current_path: Path | None = None
        self.current_handle = None
        self.current_writer = None
        self.chunk_manifests: list[dict[str, int | str]] = []

    def write_row(self, row: list[str]) -> None:
        if self.current_writer is None or self.current_rows >= self.chunk_target_rows:
            self._rotate_chunk()
        assert self.current_writer is not None
        self.current_writer.writerow(row)
        self.current_rows += 1

    def finish(self) -> list[dict[str, int | str]]:
        self._close_current_chunk()
        return list(self.chunk_manifests)

    def _rotate_chunk(self) -> None:
        self._close_current_chunk()
        self.chunk_index += 1
        events_root = self.partition_root / self.partition_key / 'events'
        events_root.mkdir(parents=True, exist_ok=True)
        self.current_path = events_root / f'{self.file_prefix}-{self.chunk_index:05d}.csv'
        self.current_handle = self.current_path.open('w', encoding='utf-8', newline='')
        self.current_writer = csv.writer(self.current_handle)
        self.current_rows = 0

    def _close_current_chunk(self) -> None:
        if self.current_handle is None or self.current_path is None:
            return
        self.current_handle.close()
        self.chunk_manifests.append(
            {
                'relative_path': self.current_path.relative_to(self.partition_root / self.partition_key).as_posix(),
                'row_count': self.current_rows,
                'size_bytes': self.current_path.stat().st_size,
            }
        )
        self.current_handle = None
        self.current_path = None
        self.current_writer = None
        self.current_rows = 0


def build_listenbrainz_identity_snapshot() -> ListenBrainzIdentitySnapshot:
    with connection.cursor() as cursor:
        cursor.execute("SELECT mbid::text, juke_id::text FROM catalog_track WHERE mbid IS NOT NULL")
        mbid_rows = cursor.fetchall()
        cursor.execute(
            """
            SELECT external_id, track_id::text
            FROM catalog_track_external_id
            WHERE source = 'spotify'
            """
        )
        spotify_rows = cursor.fetchall()
        cursor.execute(
            """
            SELECT spotify_id, juke_id::text
            FROM catalog_track
            WHERE spotify_id IS NOT NULL AND spotify_id <> ''
            """
        )
        spotify_track_rows = cursor.fetchall()

    mbid_to_track_id = {str(mbid): str(track_id) for mbid, track_id in mbid_rows if mbid and track_id}
    spotify_to_track_id = {
        str(external_id): str(track_id)
        for external_id, track_id in [*spotify_rows, *spotify_track_rows]
        if external_id and track_id
    }
    return ListenBrainzIdentitySnapshot(
        mbid_to_track_id=mbid_to_track_id,
        spotify_to_track_id=spotify_to_track_id,
    )


def _initialize_listenbrainz_extract_worker(
    identity_snapshot: ListenBrainzIdentitySnapshot,
    partition_root: str,
    run_id: str,
    partition_count: int,
    chunk_target_rows: int,
) -> None:
    global _LISTENBRAINZ_EXTRACT_IDENTITY_SNAPSHOT
    global _LISTENBRAINZ_EXTRACT_PARTITION_ROOT
    global _LISTENBRAINZ_EXTRACT_RUN_ID
    global _LISTENBRAINZ_EXTRACT_PARTITION_COUNT
    global _LISTENBRAINZ_EXTRACT_CHUNK_TARGET_ROWS

    close_old_connections()
    _LISTENBRAINZ_EXTRACT_IDENTITY_SNAPSHOT = identity_snapshot
    _LISTENBRAINZ_EXTRACT_PARTITION_ROOT = partition_root
    _LISTENBRAINZ_EXTRACT_RUN_ID = run_id
    _LISTENBRAINZ_EXTRACT_PARTITION_COUNT = partition_count
    _LISTENBRAINZ_EXTRACT_CHUNK_TARGET_ROWS = chunk_target_rows


def _process_listenbrainz_spooled_member_in_worker(
    spool_path: str,
    origin: str,
    member_token: str,
) -> ListenBrainzMemberChunkResult:
    if _LISTENBRAINZ_EXTRACT_IDENTITY_SNAPSHOT is None:
        raise RuntimeError('listenbrainz extract worker identity snapshot was not initialized')

    return _process_listenbrainz_spooled_member(
        spool_path=spool_path,
        origin=origin,
        member_token=member_token,
        partition_root=_LISTENBRAINZ_EXTRACT_PARTITION_ROOT,
        run_id=_LISTENBRAINZ_EXTRACT_RUN_ID,
        partition_count=_LISTENBRAINZ_EXTRACT_PARTITION_COUNT,
        chunk_target_rows=_LISTENBRAINZ_EXTRACT_CHUNK_TARGET_ROWS,
        identity_snapshot=_LISTENBRAINZ_EXTRACT_IDENTITY_SNAPSHOT,
    )


def partition_index_for_event(
    session_key: bytes,
    *,
    track_id: str,
    event_signature: bytes,
    partition_count: int,
) -> int:
    digest = hashlib.sha256()
    digest.update(session_key)
    if track_id:
        digest.update(track_id.encode('utf-8'))
    else:
        digest.update(event_signature)
    return int.from_bytes(digest.digest()[:8], byteorder='big') % partition_count


def _process_listenbrainz_spooled_member(
    *,
    spool_path: str,
    origin: str,
    member_token: str,
    partition_root: str,
    run_id: str,
    partition_count: int,
    chunk_target_rows: int,
    identity_snapshot: ListenBrainzIdentitySnapshot,
) -> ListenBrainzMemberChunkResult:
    counters = {
        'rows_parsed': 0,
        'rows_resolved': 0,
        'rows_unresolved': 0,
        'rows_malformed': 0,
    }
    writers: dict[str, _ListenBrainzPartitionChunkWriter] = {}

    with Path(spool_path).open('r', encoding='utf-8') as text_handle:
        for payload, error, _, line_number, entry_index in iter_listenbrainz_json_payloads(
            text_handle,
            origin=origin,
        ):
            if error:
                counters['rows_malformed'] += 1
                continue

            assert payload is not None
            try:
                parsed = parse_listenbrainz_payload(payload)
            except ValueError:
                counters['rows_malformed'] += 1
                continue

            counters['rows_parsed'] += 1
            track_id = identity_snapshot.resolve_track_id(parsed)
            if track_id:
                counters['rows_resolved'] += 1
            else:
                counters['rows_unresolved'] += 1
            partition_index = partition_index_for_event(
                parsed.session_key,
                track_id=track_id,
                event_signature=parsed.source_event_signature,
                partition_count=partition_count,
            )
            partition_key = f'p{partition_index:03d}'
            writer = writers.get(partition_key)
            if writer is None:
                writer = _ListenBrainzPartitionChunkWriter(
                    partition_root=Path(partition_root),
                    partition_key=partition_key,
                    chunk_target_rows=chunk_target_rows,
                    file_prefix=f'{member_token}-events',
                )
                writers[partition_key] = writer

            writer.write_row(
                [
                    run_id,
                    partition_key,
                    _bytea_hex(parsed.source_event_signature),
                    parsed.played_at.isoformat(),
                    _bytea_hex(parsed.session_key),
                    track_id or r'\N',
                    '1' if track_id else '0',
                    f'{origin}:{line_number}:{entry_index}',
                ]
            )

    chunk_manifests_by_partition: dict[str, list[dict[str, int | str]]] = {}
    for partition_key, writer in writers.items():
        chunk_manifests_by_partition[partition_key] = writer.finish()

    return ListenBrainzMemberChunkResult(
        member_token=member_token,
        counters=counters,
        chunk_manifests_by_partition=chunk_manifests_by_partition,
    )


def extract_listenbrainz_archive(plan: FullIngestionPlan) -> FullIngestionPlan:
    identity_snapshot = build_listenbrainz_identity_snapshot()
    chunk_target_rows = configured_full_ingestion_target_chunk_rows()
    counters = dict(plan.counters)
    running_plan = plan
    spool_root = Path(plan.run_root) / 'spool'
    spool_root.mkdir(parents=True, exist_ok=True)
    partition_chunk_manifests: dict[str, list[dict[str, int | str]]] = {
        partition.partition_key: [] for partition in plan.partitions
    }
    max_in_flight = max(1, plan.partition_workers)
    close_old_connections()

    def _record_member_result(result: ListenBrainzMemberChunkResult) -> None:
        nonlocal counters, running_plan
        counters['rows_parsed'] = int(counters.get('rows_parsed') or 0) + int(result.counters['rows_parsed'])
        counters['rows_resolved'] = int(counters.get('rows_resolved') or 0) + int(result.counters['rows_resolved'])
        counters['rows_unresolved'] = int(counters.get('rows_unresolved') or 0) + int(result.counters['rows_unresolved'])
        counters['rows_malformed'] = int(counters.get('rows_malformed') or 0) + int(result.counters['rows_malformed'])
        for partition_key, chunk_manifests in result.chunk_manifests_by_partition.items():
            partition_chunk_manifests[partition_key].extend(chunk_manifests)
        spool_path = spool_root / f'{result.member_token}.listens'
        if spool_path.exists():
            spool_path.unlink()
        running_plan = replace(
            running_plan,
            counters=dict(counters),
            updated_at=datetime.now(tz=UTC).isoformat(),
        )
        _persist_full_ingestion_state(running_plan)

    with tarfile.open(Path(plan.archive_path), 'r:*') as archive, ProcessPoolExecutor(
        max_workers=max_in_flight,
        mp_context=multiprocessing.get_context('fork'),
        initializer=_initialize_listenbrainz_extract_worker,
        initargs=(
            identity_snapshot,
            plan.partition_root,
            plan.run_id,
            plan.partition_count,
            chunk_target_rows,
        ),
    ) as executor:
        future_to_member: dict[Any, str] = {}
        member_index = 0
        for member in archive:
            relative_path = listenbrainz_shard_relative_path(member.name)
            if relative_path is None:
                continue

            extracted = archive.extractfile(member)
            if extracted is None:
                continue

            counters['artifacts_discovered'] = int(counters.get('artifacts_discovered') or 0) + 1
            counters['artifacts_partitioned'] = int(counters.get('artifacts_partitioned') or 0) + 1
            counters['input_bytes_partitioned'] = int(counters.get('input_bytes_partitioned') or 0) + int(
                member.size or 0
            )
            member_index += 1
            member_token = f'm{member_index:05d}'
            spool_path = spool_root / f'{member_token}.listens'
            with extracted, spool_path.open('wb') as spool_handle:
                shutil.copyfileobj(extracted, spool_handle, length=1024 * 1024)

            future = executor.submit(
                _process_listenbrainz_spooled_member_in_worker,
                spool_path=str(spool_path),
                origin=relative_path.as_posix(),
                member_token=member_token,
            )
            future_to_member[future] = member_token

            while len(future_to_member) >= max_in_flight:
                done, _ = wait(future_to_member.keys(), return_when=FIRST_COMPLETED)
                for done_future in done:
                    future_to_member.pop(done_future, None)
                    _record_member_result(done_future.result())

        while future_to_member:
            done, _ = wait(future_to_member.keys(), return_when=FIRST_COMPLETED)
            for done_future in done:
                future_to_member.pop(done_future, None)
                _record_member_result(done_future.result())

    finalized_partitions: list[FullIngestionPartitionPlan] = []
    total_chunks = 0
    for partition in running_plan.partitions:
        chunks = partition_chunk_manifests.get(partition.partition_key, [])
        total_chunks += len(chunks)
        write_full_ingestion_partition_manifest(
            running_plan,
            partition=partition,
            chunks=chunks,
        )
        finalized_partitions.append(
            replace(
                partition,
                state='partitioned',
                actual_input_bytes=sum(int(chunk['size_bytes']) for chunk in chunks),
                actual_artifact_count=len(chunks),
            )
        )

    completed_plan = replace(
        running_plan,
        updated_at=datetime.now(tz=UTC).isoformat(),
        counters={
            **counters,
            'chunks_written': total_chunks,
            'partitions_completed': len(finalized_partitions),
            'partitions_failed': 0,
        },
        partitions=finalized_partitions,
    )
    _persist_full_ingestion_state(completed_plan)
    return completed_plan


def ensure_listenbrainz_load_tables() -> None:
    with connection.cursor() as cursor:
        if connection.vendor == 'postgresql':
            cursor.execute(
                f'''
                CREATE UNLOGGED TABLE IF NOT EXISTS {LISTENBRAINZ_EVENT_LOAD_TABLE} (
                    run_id uuid NOT NULL,
                    partition_key varchar(16) NOT NULL,
                    event_signature bytea NOT NULL,
                    played_at timestamptz NOT NULL,
                    session_key bytea NOT NULL,
                    track_id uuid NULL,
                    resolution_state smallint NOT NULL,
                    cold_ref text NOT NULL
                )
                '''
            )
            cursor.execute(
                f'''
                CREATE INDEX IF NOT EXISTS {LISTENBRAINZ_EVENT_LOAD_TABLE}_run_partition_idx
                ON {LISTENBRAINZ_EVENT_LOAD_TABLE} (run_id, partition_key)
                '''
            )
            cursor.execute(
                f'''
                CREATE UNLOGGED TABLE IF NOT EXISTS {LISTENBRAINZ_SESSION_LOAD_TABLE} (
                    run_id uuid NOT NULL,
                    partition_key varchar(16) NOT NULL,
                    session_key bytea NOT NULL,
                    track_id uuid NOT NULL,
                    first_played_at timestamptz NOT NULL,
                    last_played_at timestamptz NOT NULL,
                    play_count integer NOT NULL
                )
                '''
            )
            cursor.execute(
                f'''
                CREATE INDEX IF NOT EXISTS {LISTENBRAINZ_SESSION_LOAD_TABLE}_run_partition_idx
                ON {LISTENBRAINZ_SESSION_LOAD_TABLE} (run_id, partition_key)
                '''
            )
        else:
            cursor.execute(
                f'''
                CREATE TABLE IF NOT EXISTS {LISTENBRAINZ_EVENT_LOAD_TABLE} (
                    run_id text NOT NULL,
                    partition_key text NOT NULL,
                    event_signature blob NOT NULL,
                    played_at text NOT NULL,
                    session_key blob NOT NULL,
                    track_id text NULL,
                    resolution_state integer NOT NULL,
                    cold_ref text NOT NULL
                )
                '''
            )
            cursor.execute(
                f'''
                CREATE INDEX IF NOT EXISTS {LISTENBRAINZ_EVENT_LOAD_TABLE}_run_partition_idx
                ON {LISTENBRAINZ_EVENT_LOAD_TABLE} (run_id, partition_key)
                '''
            )
            cursor.execute(
                f'''
                CREATE TABLE IF NOT EXISTS {LISTENBRAINZ_SESSION_LOAD_TABLE} (
                    run_id text NOT NULL,
                    partition_key text NOT NULL,
                    session_key blob NOT NULL,
                    track_id text NOT NULL,
                    first_played_at text NOT NULL,
                    last_played_at text NOT NULL,
                    play_count integer NOT NULL
                )
                '''
            )
            cursor.execute(
                f'''
                CREATE INDEX IF NOT EXISTS {LISTENBRAINZ_SESSION_LOAD_TABLE}_run_partition_idx
                ON {LISTENBRAINZ_SESSION_LOAD_TABLE} (run_id, partition_key)
                '''
            )


def load_listenbrainz_partition_to_load_tables(
    plan: FullIngestionPlan,
    partition: FullIngestionPartitionPlan,
) -> FullIngestionCopyResult:
    manifest_payload = json.loads(
        full_ingestion_partition_manifest_path(plan, partition_key=partition.partition_key).read_text(encoding='utf-8')
    )
    event_chunks = list(manifest_payload.get('event_chunks') or [])
    if not event_chunks:
        return FullIngestionCopyResult(
            partition_key=partition.partition_key,
            rows_loaded=0,
            session_rows_loaded=0,
            chunks_loaded=0,
            copy_manifest_path='',
        )

    with connection.cursor() as cursor:
        cursor.execute(
            f'DELETE FROM {LISTENBRAINZ_SESSION_LOAD_TABLE} WHERE run_id = %s AND partition_key = %s',
            [plan.run_id, partition.partition_key],
        )
        cursor.execute(
            f'DELETE FROM {LISTENBRAINZ_EVENT_LOAD_TABLE} WHERE run_id = %s AND partition_key = %s',
            [plan.run_id, partition.partition_key],
        )

    rows_loaded = 0
    chunks_loaded = 0
    for chunk in event_chunks:
        chunk_path = Path(plan.partition_root) / partition.partition_key / str(chunk['relative_path'])
        _copy_csv_into_table(
            chunk_path,
            table_name=LISTENBRAINZ_EVENT_LOAD_TABLE,
            columns=[
                'run_id',
                'partition_key',
                'event_signature',
                'played_at',
                'session_key',
                'track_id',
                'resolution_state',
                'cold_ref',
            ],
        )
        rows_loaded += int(chunk.get('row_count') or 0)
        chunks_loaded += 1

    with connection.cursor() as cursor:
        cursor.execute(
            f'''
            INSERT INTO {LISTENBRAINZ_SESSION_LOAD_TABLE} (
                run_id,
                partition_key,
                session_key,
                track_id,
                first_played_at,
                last_played_at,
                play_count
            )
            SELECT
                run_id,
                partition_key,
                session_key,
                track_id,
                MIN(played_at),
                MAX(played_at),
                COUNT(*)
            FROM {LISTENBRAINZ_EVENT_LOAD_TABLE}
            WHERE run_id = %s
              AND partition_key = %s
              AND track_id IS NOT NULL
            GROUP BY run_id, partition_key, session_key, track_id
            ''',
            [plan.run_id, partition.partition_key],
        )
        session_rows_loaded = cursor.rowcount if cursor.rowcount and cursor.rowcount > 0 else 0

    copy_manifest_path = full_ingestion_copy_manifest_path(plan, partition_key=partition.partition_key)
    return FullIngestionCopyResult(
        partition_key=partition.partition_key,
        rows_loaded=rows_loaded,
        session_rows_loaded=session_rows_loaded,
        chunks_loaded=chunks_loaded,
        copy_manifest_path=str(copy_manifest_path),
    )


def _copy_csv_into_table(csv_path: Path, *, table_name: str, columns: list[str]) -> None:
    copy_sql = f"COPY {table_name} ({', '.join(columns)}) FROM STDIN WITH (FORMAT csv, NULL '\\N')"

    if connection.vendor != 'postgresql':
        placeholders = ', '.join(['?'] * len(columns))
        insert_sql = f"INSERT INTO {table_name} ({', '.join(columns)}) VALUES ({placeholders})"
        with csv_path.open('r', encoding='utf-8', newline='') as handle, connection.cursor() as cursor:
            cursor.executemany(insert_sql, list(csv.reader(handle)))
        return

    connection.ensure_connection()
    with csv_path.open('r', encoding='utf-8', newline='') as handle:
        with connection.cursor() as cursor:
            raw_cursor = getattr(cursor, 'cursor', cursor)
            if hasattr(raw_cursor, 'copy_expert'):
                raw_cursor.copy_expert(copy_sql, handle)
                return

    raw_connection = connection.connection
    assert raw_connection is not None
    with raw_connection.cursor() as raw_cursor:
        with raw_cursor.copy(copy_sql) as copy:
            with csv_path.open('r', encoding='utf-8', newline='') as handle:
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    copy.write(chunk)


def ensure_full_ingestion_source_run(
    plan: FullIngestionPlan,
) -> tuple[SourceIngestionRun, str]:
    if plan.source_ingestion_run_id:
        try:
            run = SourceIngestionRun.objects.get(pk=plan.source_ingestion_run_id)
            return run, str(run.pk)
        except SourceIngestionRun.DoesNotExist:
            pass

    run = SourceIngestionRun.objects.create(
        source=plan.provider,
        import_mode='full',
        source_version=plan.source_version,
        raw_path=plan.archive_path,
        checksum='',
        fingerprint=plan.run_id,
        status='running',
        metadata={
            'stage': 'full_ingestion_merge',
            'full_ingestion_run_id': plan.run_id,
            'partition_count': plan.partition_count,
        },
    )
    return run, str(run.pk)


def finalize_full_ingestion_source_run(
    source_ingestion_run: SourceIngestionRun,
    plan: FullIngestionPlan,
) -> None:
    source_ingestion_run.status = 'succeeded'
    source_ingestion_run.imported_row_count = int(plan.counters.get('rows_merged') or 0)
    source_ingestion_run.duplicate_row_count = int(plan.counters.get('rows_deduplicated') or 0)
    source_ingestion_run.canonicalized_row_count = int(plan.counters.get('rows_merged') or 0)
    source_ingestion_run.unresolved_row_count = int(plan.counters.get('rows_unresolved') or 0)
    source_ingestion_run.malformed_row_count = int(plan.counters.get('rows_malformed') or 0)
    source_ingestion_run.source_row_count = int(plan.counters.get('rows_parsed') or 0)
    source_ingestion_run.completed_at = timezone.now()
    source_ingestion_run.metadata = {
        **source_ingestion_run.metadata,
        'stage': 'completed',
        'full_ingestion_run_id': plan.run_id,
        'partitions_loaded': int(plan.counters.get('partitions_loaded') or 0),
        'partitions_merged': int(plan.counters.get('partitions_merged') or 0),
    }
    source_ingestion_run.save(
        update_fields=[
            'status',
            'source_row_count',
            'imported_row_count',
            'duplicate_row_count',
            'canonicalized_row_count',
            'unresolved_row_count',
            'malformed_row_count',
            'completed_at',
            'metadata',
        ]
    )


def _mark_full_ingestion_source_run_failed(
    source_ingestion_run: SourceIngestionRun,
    plan: FullIngestionPlan,
    *,
    error: str,
) -> None:
    source_ingestion_run.status = 'failed'
    source_ingestion_run.last_error = error
    source_ingestion_run.completed_at = timezone.now()
    source_ingestion_run.source_row_count = int(plan.counters.get('rows_parsed') or 0)
    source_ingestion_run.imported_row_count = int(plan.counters.get('rows_merged') or 0)
    source_ingestion_run.duplicate_row_count = int(plan.counters.get('rows_deduplicated') or 0)
    source_ingestion_run.canonicalized_row_count = int(plan.counters.get('rows_merged') or 0)
    source_ingestion_run.unresolved_row_count = int(plan.counters.get('rows_unresolved') or 0)
    source_ingestion_run.malformed_row_count = int(plan.counters.get('rows_malformed') or 0)
    source_ingestion_run.metadata = {
        **source_ingestion_run.metadata,
        'stage': 'failed',
        'full_ingestion_run_id': plan.run_id,
    }
    source_ingestion_run.save(
        update_fields=[
            'status',
            'last_error',
            'completed_at',
            'source_row_count',
            'imported_row_count',
            'duplicate_row_count',
            'canonicalized_row_count',
            'unresolved_row_count',
            'malformed_row_count',
            'metadata',
        ]
    )


def finalize_listenbrainz_full_ingestion(
    plan: FullIngestionPlan,
    *,
    source_ingestion_run: SourceIngestionRun,
) -> FullIngestionMergeResult:
    if connection.vendor != 'postgresql':
        return finalize_listenbrainz_full_ingestion_direct(
            plan,
            source_ingestion_run=source_ingestion_run,
        )

    with connection.cursor() as cursor:
        _drop_listenbrainz_shadow_tables(cursor)
        staged_rows = _count_load_rows(cursor, LISTENBRAINZ_EVENT_LOAD_TABLE, plan.run_id)
        _create_listenbrainz_event_ledger_build_table(
            cursor,
            run_id=plan.run_id,
            import_run_id=str(source_ingestion_run.pk),
        )
        _create_listenbrainz_session_track_build_table(
            cursor,
            run_id=plan.run_id,
            import_run_id=str(source_ingestion_run.pk),
        )
        inserted_rows = _count_table_rows(cursor, LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE)
        resolved_rows = _count_table_rows(
            cursor,
            LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE,
            where_clause='track_id IS NOT NULL',
        )
        unresolved_rows = _count_table_rows(
            cursor,
            LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE,
            where_clause='track_id IS NULL',
        )
        session_rows_merged = _count_table_rows(cursor, LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE)
        _create_listenbrainz_shadow_constraints_and_indexes(cursor)
        _swap_listenbrainz_shadow_tables(cursor)
        cursor.execute(
            f'DELETE FROM {LISTENBRAINZ_SESSION_LOAD_TABLE} WHERE run_id = %s',
            [plan.run_id],
        )
        cursor.execute(
            f'DELETE FROM {LISTENBRAINZ_EVENT_LOAD_TABLE} WHERE run_id = %s',
            [plan.run_id],
        )
        cursor.execute(f'ANALYZE {LISTENBRAINZ_EVENT_LEDGER_TABLE}')
        cursor.execute(f'ANALYZE {LISTENBRAINZ_SESSION_TRACK_TABLE}')

    return FullIngestionMergeResult(
        rows_merged=int(inserted_rows),
        rows_deduplicated=max(0, int(staged_rows) - int(inserted_rows)),
        rows_resolved=int(resolved_rows),
        rows_unresolved=int(unresolved_rows),
        session_rows_merged=int(session_rows_merged),
    )


def finalize_listenbrainz_full_ingestion_direct(
    plan: FullIngestionPlan,
    *,
    source_ingestion_run: SourceIngestionRun,
) -> FullIngestionMergeResult:
    with connection.cursor() as cursor:
        cursor.execute(
            f'DELETE FROM {LISTENBRAINZ_SESSION_TRACK_TABLE} WHERE import_run_id = %s',
            [str(source_ingestion_run.pk)],
        )
        cursor.execute(
            f'DELETE FROM {LISTENBRAINZ_EVENT_LEDGER_TABLE} WHERE import_run_id = %s',
            [str(source_ingestion_run.pk)],
        )
        cursor.execute(
            f'''
            WITH staged_rows AS (
                SELECT
                    event_signature,
                    played_at,
                    session_key,
                    track_id,
                    resolution_state,
                    cold_ref
                FROM {LISTENBRAINZ_EVENT_LOAD_TABLE}
                WHERE run_id = %s
            ),
            deduplicated_events AS (
                SELECT DISTINCT ON (event_signature)
                    event_signature,
                    played_at,
                    session_key,
                    track_id,
                    resolution_state,
                    cold_ref
                FROM staged_rows
                ORDER BY event_signature, cold_ref
            ),
            inserted_events AS (
                INSERT INTO {LISTENBRAINZ_EVENT_LEDGER_TABLE} (
                    id,
                    import_run_id,
                    event_signature,
                    played_at,
                    session_key,
                    track_id,
                    resolution_state,
                    cold_ref,
                    created_at
                )
                SELECT
                    {deterministic_uuid_sql("encode(deduplicated_events.event_signature, 'hex')")},
                    %s,
                    deduplicated_events.event_signature,
                    deduplicated_events.played_at,
                    deduplicated_events.session_key,
                    deduplicated_events.track_id,
                    deduplicated_events.resolution_state,
                    deduplicated_events.cold_ref,
                    NOW()
                FROM deduplicated_events
                ON CONFLICT (event_signature) DO NOTHING
                RETURNING track_id
            ),
            upserted_session_tracks AS (
                INSERT INTO {LISTENBRAINZ_SESSION_TRACK_TABLE} (
                    id,
                    import_run_id,
                    session_key,
                    track_id,
                    first_played_at,
                    last_played_at,
                    play_count,
                    created_at
                )
                SELECT
                    {
                        deterministic_uuid_sql(
                            "encode(session_delta.session_key, 'hex') || ':' || "
                            "session_delta.track_id::text"
                        )
                    },
                    %s,
                    session_delta.session_key,
                    session_delta.track_id,
                    session_delta.first_played_at,
                    session_delta.last_played_at,
                    session_delta.play_count,
                    NOW()
                FROM {LISTENBRAINZ_SESSION_LOAD_TABLE} session_delta
                WHERE session_delta.run_id = %s
                ON CONFLICT (session_key, track_id) DO UPDATE
                SET
                    first_played_at = LEAST(
                        {LISTENBRAINZ_SESSION_TRACK_TABLE}.first_played_at,
                        EXCLUDED.first_played_at
                    ),
                    last_played_at = GREATEST(
                        {LISTENBRAINZ_SESSION_TRACK_TABLE}.last_played_at,
                        EXCLUDED.last_played_at
                    ),
                    play_count = {LISTENBRAINZ_SESSION_TRACK_TABLE}.play_count + EXCLUDED.play_count
                RETURNING 1
            )
            SELECT
                COALESCE((SELECT COUNT(*) FROM staged_rows), 0) AS staged_rows,
                COALESCE((SELECT COUNT(*) FROM inserted_events), 0) AS inserted_rows,
                COALESCE((SELECT COUNT(*) FROM inserted_events WHERE track_id IS NOT NULL), 0) AS resolved_rows,
                COALESCE((SELECT COUNT(*) FROM inserted_events WHERE track_id IS NULL), 0) AS unresolved_rows,
                COALESCE((SELECT COUNT(*) FROM upserted_session_tracks), 0) AS session_rows_merged
            ''',
            [
                plan.run_id,
                str(source_ingestion_run.pk),
                str(source_ingestion_run.pk),
                plan.run_id,
            ],
        )
        staged_rows, inserted_rows, resolved_rows, unresolved_rows, session_rows_merged = cursor.fetchone()
        cursor.execute(
            f'DELETE FROM {LISTENBRAINZ_SESSION_LOAD_TABLE} WHERE run_id = %s',
            [plan.run_id],
        )
        cursor.execute(
            f'DELETE FROM {LISTENBRAINZ_EVENT_LOAD_TABLE} WHERE run_id = %s',
            [plan.run_id],
        )

    return FullIngestionMergeResult(
        rows_merged=int(inserted_rows or 0),
        rows_deduplicated=max(0, int(staged_rows or 0) - int(inserted_rows or 0)),
        rows_resolved=int(resolved_rows or 0),
        rows_unresolved=int(unresolved_rows or 0),
        session_rows_merged=int(session_rows_merged or 0),
    )


def _count_load_rows(cursor, table_name: str, run_id: str) -> int:
    cursor.execute(f'SELECT COUNT(*) FROM {table_name} WHERE run_id = %s', [run_id])
    return int(cursor.fetchone()[0] or 0)


def _count_table_rows(cursor, table_name: str, *, where_clause: str = '') -> int:
    where_sql = f' WHERE {where_clause}' if where_clause else ''
    cursor.execute(f'SELECT COUNT(*) FROM {table_name}{where_sql}')
    return int(cursor.fetchone()[0] or 0)


def _drop_listenbrainz_shadow_tables(cursor) -> None:
    for table_name in (
        LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE,
        LISTENBRAINZ_EVENT_LEDGER_BACKUP_TABLE,
        LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE,
        LISTENBRAINZ_SESSION_TRACK_BACKUP_TABLE,
    ):
        cursor.execute(f'DROP TABLE IF EXISTS {table_name} CASCADE')


def _create_listenbrainz_event_ledger_build_table(cursor, *, run_id: str, import_run_id: str) -> None:
    cursor.execute(
        f'''
        CREATE TABLE {LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE}
        TABLESPACE {settings.MLCORE_PG_COLD_TABLESPACE_NAME}
        AS
        WITH deduplicated_events AS (
            SELECT DISTINCT ON (event_signature)
                event_signature,
                played_at,
                session_key,
                track_id,
                resolution_state,
                cold_ref
            FROM {LISTENBRAINZ_EVENT_LOAD_TABLE}
            WHERE run_id = %s
            ORDER BY event_signature, cold_ref
        )
        SELECT
            {deterministic_uuid_sql("encode(deduplicated_events.event_signature, 'hex')")} AS id,
            %s::uuid AS import_run_id,
            deduplicated_events.event_signature,
            deduplicated_events.played_at,
            deduplicated_events.session_key,
            deduplicated_events.track_id,
            deduplicated_events.resolution_state,
            deduplicated_events.cold_ref,
            NOW() AS created_at
        FROM deduplicated_events
        ''',
        [run_id, import_run_id],
    )
    for column_name in (
        'id',
        'import_run_id',
        'event_signature',
        'played_at',
        'session_key',
        'resolution_state',
        'cold_ref',
        'created_at',
    ):
        cursor.execute(
            f'ALTER TABLE {LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE} ALTER COLUMN {column_name} SET NOT NULL'
        )


def _create_listenbrainz_session_track_build_table(cursor, *, run_id: str, import_run_id: str) -> None:
    cursor.execute(
        f'''
        CREATE TABLE {LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE}
        TABLESPACE {settings.MLCORE_PG_HOT_TABLESPACE_NAME}
        AS
        SELECT
            {
                deterministic_uuid_sql(
                    "encode(session_delta.session_key, 'hex') || ':' || session_delta.track_id::text"
                )
            } AS id,
            %s::uuid AS import_run_id,
            session_delta.session_key,
            session_delta.track_id,
            MIN(session_delta.first_played_at) AS first_played_at,
            MAX(session_delta.last_played_at) AS last_played_at,
            SUM(session_delta.play_count)::integer AS play_count,
            NOW() AS created_at
        FROM {LISTENBRAINZ_SESSION_LOAD_TABLE} session_delta
        WHERE session_delta.run_id = %s
        GROUP BY session_delta.session_key, session_delta.track_id
        ''',
        [import_run_id, run_id],
    )
    for column_name in (
        'id',
        'session_key',
        'track_id',
        'first_played_at',
        'last_played_at',
        'play_count',
        'created_at',
    ):
        cursor.execute(
            f'ALTER TABLE {LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE} ALTER COLUMN {column_name} SET NOT NULL'
        )


def _create_listenbrainz_shadow_constraints_and_indexes(cursor) -> None:
    event_cold_ts = settings.MLCORE_PG_COLD_TABLESPACE_NAME
    session_hot_ts = settings.MLCORE_PG_HOT_TABLESPACE_NAME

    cursor.execute(
        (
            f'CREATE UNIQUE INDEX mlcore_lbe_build_pkey_idx '
            f'ON {LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE} (id) TABLESPACE {event_cold_ts}'
        )
    )
    cursor.execute(
        (
            f'ALTER TABLE {LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE} '
            f'ADD CONSTRAINT mlcore_lbe_build_pkey '
            f'PRIMARY KEY USING INDEX mlcore_lbe_build_pkey_idx'
        )
    )
    cursor.execute(
        (
            f'CREATE UNIQUE INDEX mlcore_lbe_build_event_signature_idx '
            f'ON {LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE} (event_signature) '
            f'TABLESPACE {event_cold_ts}'
        )
    )
    cursor.execute(
        (
            f'ALTER TABLE {LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE} '
            f'ADD CONSTRAINT mlcore_lbe_build_event_signature_key '
            f'UNIQUE USING INDEX mlcore_lbe_build_event_signature_idx'
        )
    )
    cursor.execute(
        (
            f'ALTER TABLE {LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE} '
            f'ADD CONSTRAINT mlcore_lbe_build_resolution_state_check '
            f'CHECK (resolution_state >= 0)'
        )
    )
    cursor.execute(
        (
            f'ALTER TABLE {LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE} '
            f'ADD CONSTRAINT mlcore_lbe_build_import_run_fk '
            f'FOREIGN KEY (import_run_id) REFERENCES mlcore_source_ingestion_run(id) '
            f'DEFERRABLE INITIALLY DEFERRED'
        )
    )
    cursor.execute(
        (
            f'ALTER TABLE {LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE} '
            f'ADD CONSTRAINT mlcore_lbe_build_track_fk '
            f'FOREIGN KEY (track_id) REFERENCES catalog_track(juke_id) '
            f'DEFERRABLE INITIALLY DEFERRED'
        )
    )
    for index_name, column_list in (
        ('mlcore_lbe_build_import_idx', 'import_run_id'),
        ('mlcore_lbe_build_track_idx', 'track_id'),
        ('mlcore_lbe_build_resolution_idx', 'resolution_state'),
        ('mlcore_lbe_build_import_run_fk_idx', 'import_run_id'),
        ('mlcore_lbe_build_played_at_idx', 'played_at'),
        ('mlcore_lbe_build_session_key_idx', 'session_key'),
        ('mlcore_lbe_build_track_fk_idx', 'track_id'),
    ):
        cursor.execute(
            f'CREATE INDEX {index_name} ON {LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE} ({column_list}) TABLESPACE {event_cold_ts}'
        )

    cursor.execute(
        (
            f'CREATE UNIQUE INDEX mlcore_lst_build_pkey_idx '
            f'ON {LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE} (id) TABLESPACE {session_hot_ts}'
        )
    )
    cursor.execute(
        (
            f'ALTER TABLE {LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE} '
            f'ADD CONSTRAINT mlcore_lst_build_pkey '
            f'PRIMARY KEY USING INDEX mlcore_lst_build_pkey_idx'
        )
    )
    cursor.execute(
        (
            f'CREATE UNIQUE INDEX mlcore_lst_build_session_track_idx '
            f'ON {LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE} (session_key, track_id) '
            f'TABLESPACE {session_hot_ts}'
        )
    )
    cursor.execute(
        (
            f'ALTER TABLE {LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE} '
            f'ADD CONSTRAINT mlcore_lst_build_session_track_key '
            f'UNIQUE USING INDEX mlcore_lst_build_session_track_idx'
        )
    )
    cursor.execute(
        (
            f'ALTER TABLE {LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE} '
            f'ADD CONSTRAINT mlcore_lst_build_import_run_fk '
            f'FOREIGN KEY (import_run_id) REFERENCES mlcore_source_ingestion_run(id) '
            f'DEFERRABLE INITIALLY DEFERRED'
        )
    )
    cursor.execute(
        (
            f'ALTER TABLE {LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE} '
            f'ADD CONSTRAINT mlcore_lst_build_track_fk '
            f'FOREIGN KEY (track_id) REFERENCES catalog_track(juke_id) '
            f'DEFERRABLE INITIALLY DEFERRED'
        )
    )
    for index_name, column_list in (
        ('mlcore_lst_build_track_idx', 'track_id'),
        ('mlcore_lst_build_import_idx', 'import_run_id'),
        ('mlcore_lst_build_last_played_idx', 'last_played_at'),
        ('mlcore_lst_build_import_run_fk_idx', 'import_run_id'),
        ('mlcore_lst_build_session_key_idx', 'session_key'),
        ('mlcore_lst_build_track_fk_idx', 'track_id'),
    ):
        cursor.execute(
            f'CREATE INDEX {index_name} ON {LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE} ({column_list}) TABLESPACE {session_hot_ts}'
        )


def _swap_listenbrainz_shadow_tables(cursor) -> None:
    with transaction.atomic():
        cursor.execute(
            f'LOCK TABLE {LISTENBRAINZ_EVENT_LEDGER_TABLE}, {LISTENBRAINZ_SESSION_TRACK_TABLE} IN ACCESS EXCLUSIVE MODE'
        )
        cursor.execute(
            f'ALTER TABLE {LISTENBRAINZ_EVENT_LEDGER_TABLE} RENAME TO {LISTENBRAINZ_EVENT_LEDGER_BACKUP_TABLE}'
        )
        cursor.execute(
            f'ALTER TABLE {LISTENBRAINZ_SESSION_TRACK_TABLE} RENAME TO {LISTENBRAINZ_SESSION_TRACK_BACKUP_TABLE}'
        )
        cursor.execute(
            f'ALTER TABLE {LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE} RENAME TO {LISTENBRAINZ_EVENT_LEDGER_TABLE}'
        )
        cursor.execute(
            f'ALTER TABLE {LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE} RENAME TO {LISTENBRAINZ_SESSION_TRACK_TABLE}'
        )
        cursor.execute(f'DROP TABLE {LISTENBRAINZ_EVENT_LEDGER_BACKUP_TABLE} CASCADE')
        cursor.execute(f'DROP TABLE {LISTENBRAINZ_SESSION_TRACK_BACKUP_TABLE} CASCADE')

        for old_name, new_name in (
            ('mlcore_lbe_build_pkey', 'mlcore_listenbrainz_event_ledger_pkey'),
            ('mlcore_lbe_build_event_signature_key', 'mlcore_listenbrainz_event_ledger_event_signature_key'),
            ('mlcore_lbe_build_resolution_state_check', 'mlcore_listenbrainz_event_ledger_resolution_state_check'),
            ('mlcore_lbe_build_import_run_fk', 'mlcore_listenbrainz__import_run_id_caebef5c_fk_mlcore_so'),
            ('mlcore_lbe_build_track_fk', 'mlcore_listenbrainz__track_id_3f187a0b_fk_catalog_t'),
        ):
            cursor.execute(
                f'ALTER TABLE {LISTENBRAINZ_EVENT_LEDGER_TABLE} RENAME CONSTRAINT {old_name} TO {new_name}'
            )

        for old_name, new_name in (
            ('mlcore_lbe_build_import_idx', 'mlcore_lbe_import__e9179a_idx'),
            ('mlcore_lbe_build_track_idx', 'mlcore_lbe_track_i_4c8647_idx'),
            ('mlcore_lbe_build_resolution_idx', 'mlcore_lbe_resolut_8e2ae0_idx'),
            ('mlcore_lbe_build_import_run_fk_idx', 'mlcore_listenbrainz_event_ledger_import_run_id_caebef5c'),
            ('mlcore_lbe_build_played_at_idx', 'mlcore_listenbrainz_event_ledger_played_at_dac9bed0'),
            ('mlcore_lbe_build_session_key_idx', 'mlcore_listenbrainz_event_ledger_session_key_1515c241'),
            ('mlcore_lbe_build_track_fk_idx', 'mlcore_listenbrainz_event_ledger_track_id_3f187a0b'),
        ):
            cursor.execute(f'ALTER INDEX {old_name} RENAME TO {new_name}')

        for old_name, new_name in (
            ('mlcore_lst_build_pkey', 'mlcore_listenbrainz_session_track_pkey'),
            ('mlcore_lst_build_session_track_key', 'mlcore_listenbrainz_sess_session_key_track_id_598560ee_uniq'),
            ('mlcore_lst_build_import_run_fk', 'mlcore_listenbrainz__import_run_id_a2d035d9_fk_mlcore_so'),
            ('mlcore_lst_build_track_fk', 'mlcore_listenbrainz__track_id_7ed8fb5a_fk_catalog_t'),
        ):
            cursor.execute(
                f'ALTER TABLE {LISTENBRAINZ_SESSION_TRACK_TABLE} RENAME CONSTRAINT {old_name} TO {new_name}'
            )

        for old_name, new_name in (
            ('mlcore_lst_build_track_idx', 'mlcore_lst_track_i_5d5e20_idx'),
            ('mlcore_lst_build_import_idx', 'mlcore_lst_import__6d7bf6_idx'),
            ('mlcore_lst_build_last_played_idx', 'mlcore_lst_last_pl_4a4ec9_idx'),
            ('mlcore_lst_build_import_run_fk_idx', 'mlcore_listenbrainz_session_track_import_run_id_a2d035d9'),
            ('mlcore_lst_build_session_key_idx', 'mlcore_listenbrainz_session_track_session_key_33f13768'),
            ('mlcore_lst_build_track_fk_idx', 'mlcore_listenbrainz_session_track_track_id_7ed8fb5a'),
        ):
            cursor.execute(f'ALTER INDEX {old_name} RENAME TO {new_name}')


def deterministic_uuid_sql(expression: str) -> str:
    return (
        f"("
        f"substr(md5({expression}), 1, 8) || '-' || "
        f"substr(md5({expression}), 9, 4) || '-' || "
        f"substr(md5({expression}), 13, 4) || '-' || "
        f"substr(md5({expression}), 17, 4) || '-' || "
        f"substr(md5({expression}), 21, 12)"
        f")::uuid"
    )


def _bytea_hex(value: bytes) -> str:
    return '\\x' + value.hex()
