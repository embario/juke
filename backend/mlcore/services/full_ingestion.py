from __future__ import annotations

import csv
import hashlib
import json
import multiprocessing
import os
import shutil
import tarfile
import threading
import time
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
from mlcore.services.canonical_items import (
    identity_from_listenbrainz_candidates,
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
    'chunk_bytes_written',
    'spool_bytes_estimated',
    'spooled_members_in_flight',
    'scratch_actual_bytes',
    'host_device_util_milli_pct',
    'host_iowait_milli_pct',
    'host_available_memory_bytes',
    'host_swap_used_bytes',
    'rows_parsed',
    'rows_with_mbid_candidate',
    'rows_with_spotify_candidate',
    'rows_with_no_candidate',
    'rows_staged',
    'session_rows_loaded',
    'rows_merged',
    'rows_deduplicated',
    'rows_resolved',
    'rows_resolved_by_mbid',
    'rows_resolved_by_spotify',
    'rows_unresolved',
    'rows_malformed',
    'chunks_written',
    'chunks_loaded',
    'partitions_completed',
    'partitions_loaded',
    'partitions_merged',
    'partitions_failed',
    'cold_build_complete',
    'hot_stage_complete',
    'hot_build_partitions_completed',
    'hot_build_complete',
    'shadow_indexes_complete',
    'swap_completed',
)
LISTENBRAINZ_EVENT_LOAD_TABLE = 'mlcore_listenbrainz_event_load'
LISTENBRAINZ_SESSION_LOAD_TABLE = 'mlcore_listenbrainz_session_delta_load'
LISTENBRAINZ_SESSION_STAGE_TABLE = 'mlcore_listenbrainz_session_track_stage'
LISTENBRAINZ_FINALIZE_CHECKPOINT_TABLE = 'mlcore_listenbrainz_finalize_checkpoint'
CANONICAL_ITEM_TABLE = 'mlcore_canonical_item'
LISTENBRAINZ_EVENT_LEDGER_TABLE = 'mlcore_listenbrainz_event_ledger'
LISTENBRAINZ_SESSION_TRACK_TABLE = 'mlcore_listenbrainz_session_track'
LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE = 'mlcore_listenbrainz_event_ledger_build'
LISTENBRAINZ_EVENT_LEDGER_BACKUP_TABLE = 'mlcore_listenbrainz_event_ledger_old'
LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE = 'mlcore_listenbrainz_session_track_build'
LISTENBRAINZ_SESSION_TRACK_BACKUP_TABLE = 'mlcore_listenbrainz_session_track_old'
LISTENBRAINZ_FINALIZE_PHASE_PARTITION_DRAIN = 'partition_drain'
LISTENBRAINZ_FINALIZE_PHASE_HOT_BUILD = 'hot_build_partition'
LISTENBRAINZ_FINALIZE_PHASE_HOT_BUILD_LEGACY = 'hot_build_legacy'
LISTENBRAINZ_FINALIZE_PHASE_SHADOW_INDEXES = 'shadow_indexes'
LISTENBRAINZ_FINALIZE_PHASE_SWAP = 'swap'
FULL_INGESTION_POLICY_INTERACTIVE = 'interactive'
FULL_INGESTION_POLICY_THROUGHPUT = 'throughput'
FULL_INGESTION_POLICY_CHOICES = (
    FULL_INGESTION_POLICY_INTERACTIVE,
    FULL_INGESTION_POLICY_THROUGHPUT,
)
_LISTENBRAINZ_EXTRACT_IDENTITY_SNAPSHOT: ListenBrainzIdentitySnapshot | None = None
_LISTENBRAINZ_EXTRACT_PARTITION_ROOT: str = ''
_LISTENBRAINZ_EXTRACT_RUN_ID: str = ''
_LISTENBRAINZ_EXTRACT_PARTITION_COUNT: int = 0
_LISTENBRAINZ_EXTRACT_CHUNK_TARGET_ROWS: int = 0
_FULL_INGESTION_PRESSURE_STATE: dict[str, HostPressureState] = {}


class FullIngestionLeaseHeldError(RuntimeError):
    pass


@dataclass
class HostPressureState:
    sampled_at: float
    device_io_ms: int
    total_cpu_ticks: int
    total_iowait_ticks: int
    soft_pressure_streak: int = 0
    hard_pressure_streak: int = 0
    recovery_streak: int = 0


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
    spool_size_bytes: int
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
    control_path: str
    metrics_path: str
    partition_count: int
    partition_workers: int
    load_workers: int
    merge_workers: int
    policy_mode: str
    partition_worker_budget: int
    load_worker_budget: int
    merge_worker_budget: int
    scratch_soft_cap_bytes: int
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
        force: bool = False,
    ) -> tuple[FullIngestionMergeResult, list[FullIngestionPartitionPlan]]:
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
        force: bool = False,
    ) -> tuple[FullIngestionMergeResult, list[FullIngestionPartitionPlan]]:
        return finalize_listenbrainz_full_ingestion(
            plan,
            source_ingestion_run=source_ingestion_run,
            force=force,
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


def configured_full_ingestion_default_policy_mode() -> str:
    value = str(
        getattr(settings, 'MLCORE_FULL_INGESTION_DEFAULT_POLICY_MODE', FULL_INGESTION_POLICY_INTERACTIVE)
    ).strip().casefold()
    if value not in FULL_INGESTION_POLICY_CHOICES:
        return FULL_INGESTION_POLICY_INTERACTIVE
    return value


def configured_full_ingestion_scratch_soft_cap_bytes() -> int:
    return max(1, int(getattr(settings, 'MLCORE_FULL_INGESTION_SCRATCH_SOFT_CAP_BYTES', 500 * 1024**3)))


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


def full_ingestion_control_path(
    *,
    provider: str,
    source_version: str,
    scratch_root: str | Path | None = None,
) -> Path:
    return full_ingestion_run_root(
        provider=provider,
        source_version=source_version,
        scratch_root=scratch_root,
    ) / 'control.json'


def full_ingestion_partition_state_counts(
    plan: FullIngestionPlan,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for partition in plan.partitions:
        counts[partition.state] = counts.get(partition.state, 0) + 1
    return counts


def _default_worker_budget(configured_workers: int, *, policy_mode: str, interactive_cap: int) -> int:
    if policy_mode == FULL_INGESTION_POLICY_THROUGHPUT:
        return max(1, configured_workers)
    return max(1, min(configured_workers, interactive_cap))


def _normalize_policy_mode(policy_mode: str | None) -> str:
    normalized = str(policy_mode or '').strip().casefold()
    if normalized not in FULL_INGESTION_POLICY_CHOICES:
        return configured_full_ingestion_default_policy_mode()
    return normalized


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
    resolved_policy_mode = configured_full_ingestion_default_policy_mode()
    resolved_partition_budget = _default_worker_budget(
        resolved_partition_workers,
        policy_mode=resolved_policy_mode,
        interactive_cap=8,
    )
    resolved_load_budget = _default_worker_budget(
        resolved_load_workers,
        policy_mode=resolved_policy_mode,
        interactive_cap=2,
    )
    resolved_merge_budget = _default_worker_budget(
        resolved_merge_workers,
        policy_mode=resolved_policy_mode,
        interactive_cap=1,
    )
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
        control_path=str(
            full_ingestion_control_path(
                provider=ingestion_provider.provider,
                source_version=resolved_source_version,
                scratch_root=resolved_scratch_root,
            )
        ),
        metrics_path=str(resolved_metrics_path or ''),
        partition_count=resolved_partition_count,
        partition_workers=resolved_partition_workers,
        load_workers=resolved_load_workers,
        merge_workers=resolved_merge_workers,
        policy_mode=resolved_policy_mode,
        partition_worker_budget=resolved_partition_budget,
        load_worker_budget=resolved_load_budget,
        merge_worker_budget=resolved_merge_budget,
        scratch_soft_cap_bytes=configured_full_ingestion_scratch_soft_cap_bytes(),
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
        'control_path': plan.control_path,
        'metrics_path': plan.metrics_path,
        'partition_count': plan.partition_count,
        'worker_config': {
            'partition_workers': plan.partition_workers,
            'load_workers': plan.load_workers,
            'merge_workers': plan.merge_workers,
        },
        'runtime_control': {
            'policy_mode': plan.policy_mode,
            'partition_worker_budget': plan.partition_worker_budget,
            'load_worker_budget': plan.load_worker_budget,
            'merge_worker_budget': plan.merge_worker_budget,
            'scratch_soft_cap_bytes': plan.scratch_soft_cap_bytes,
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
    runtime_control = dict(payload.get('runtime_control') or {})
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
        control_path=str(
            payload.get('control_path')
            or full_ingestion_control_path(
                provider=str(payload['provider']),
                source_version=str(payload['source_version']),
                scratch_root=str(payload['scratch_root']),
            )
        ),
        metrics_path=str(payload.get('metrics_path') or ''),
        partition_count=int(payload['partition_count']),
        partition_workers=int(worker_config.get('partition_workers') or 0),
        load_workers=int(worker_config.get('load_workers') or 0),
        merge_workers=int(worker_config.get('merge_workers') or 0),
        policy_mode=_normalize_policy_mode(runtime_control.get('policy_mode')),
        partition_worker_budget=int(
            runtime_control.get('partition_worker_budget')
            or _default_worker_budget(
                int(worker_config.get('partition_workers') or 1),
                policy_mode=_normalize_policy_mode(runtime_control.get('policy_mode')),
                interactive_cap=8,
            )
        ),
        load_worker_budget=int(
            runtime_control.get('load_worker_budget')
            or _default_worker_budget(
                int(worker_config.get('load_workers') or 1),
                policy_mode=_normalize_policy_mode(runtime_control.get('policy_mode')),
                interactive_cap=2,
            )
        ),
        merge_worker_budget=int(
            runtime_control.get('merge_worker_budget')
            or _default_worker_budget(
                int(worker_config.get('merge_workers') or 1),
                policy_mode=_normalize_policy_mode(runtime_control.get('policy_mode')),
                interactive_cap=1,
            )
        ),
        scratch_soft_cap_bytes=int(
            runtime_control.get('scratch_soft_cap_bytes') or configured_full_ingestion_scratch_soft_cap_bytes()
        ),
        total_estimated_uncompressed_bytes=int(payload.get('total_estimated_uncompressed_bytes') or 0),
        source_ingestion_run_id=str(payload.get('source_ingestion_run_id') or ''),
        stage=str(payload['stage']),
        status=str(payload['status']),
        created_at=str(payload['created_at']),
        updated_at=str(payload['updated_at']),
        counters=counters,
        partitions=partitions,
    )


def read_full_ingestion_control(plan: FullIngestionPlan) -> dict[str, Any]:
    control_path = Path(plan.control_path)
    if not control_path.exists():
        return {
            'policy_mode': plan.policy_mode,
            'partition_worker_budget': plan.partition_worker_budget,
            'load_worker_budget': plan.load_worker_budget,
            'merge_worker_budget': plan.merge_worker_budget,
            'scratch_soft_cap_bytes': plan.scratch_soft_cap_bytes,
        }
    return json.loads(control_path.read_text(encoding='utf-8'))


def write_full_ingestion_control(
    plan: FullIngestionPlan,
    *,
    policy_mode: str | None = None,
    partition_worker_budget: int | None = None,
    partition_worker_budget_cap: int | None = None,
    load_worker_budget: int | None = None,
    load_worker_budget_cap: int | None = None,
    merge_worker_budget: int | None = None,
    merge_worker_budget_cap: int | None = None,
    scratch_soft_cap_bytes: int | None = None,
) -> Path:
    existing_payload = read_full_ingestion_control(plan)
    payload = {
        'policy_mode': _normalize_policy_mode(policy_mode or plan.policy_mode),
        'partition_worker_budget': max(
            1,
            min(
                plan.partition_workers,
                int(partition_worker_budget or plan.partition_worker_budget),
            ),
        ),
        'partition_worker_budget_cap': max(
            1,
            min(
                plan.partition_workers,
                int(
                    partition_worker_budget_cap
                    or existing_payload.get('partition_worker_budget_cap')
                    or existing_payload.get('partition_worker_budget')
                    or plan.partition_worker_budget
                ),
            ),
        ),
        'load_worker_budget': max(
            1,
            min(
                plan.load_workers,
                int(load_worker_budget or plan.load_worker_budget),
            ),
        ),
        'load_worker_budget_cap': max(
            1,
            min(
                plan.load_workers,
                int(
                    load_worker_budget_cap
                    or existing_payload.get('load_worker_budget_cap')
                    or existing_payload.get('load_worker_budget')
                    or plan.load_worker_budget
                ),
            ),
        ),
        'merge_worker_budget': max(
            1,
            min(
                plan.merge_workers,
                int(merge_worker_budget or plan.merge_worker_budget),
            ),
        ),
        'merge_worker_budget_cap': max(
            1,
            min(
                plan.merge_workers,
                int(
                    merge_worker_budget_cap
                    or existing_payload.get('merge_worker_budget_cap')
                    or existing_payload.get('merge_worker_budget')
                    or plan.merge_worker_budget
                ),
            ),
        ),
        'scratch_soft_cap_bytes': max(
            1,
            int(scratch_soft_cap_bytes or plan.scratch_soft_cap_bytes),
        ),
    }
    control_path = Path(plan.control_path)
    control_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = control_path.with_name(control_path.name + '.tmp')
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + '\n', encoding='utf-8')
    temp_path.replace(control_path)
    return control_path


def sync_full_ingestion_runtime_control(plan: FullIngestionPlan) -> FullIngestionPlan:
    payload = read_full_ingestion_control(plan)
    return replace(
        plan,
        policy_mode=_normalize_policy_mode(payload.get('policy_mode')),
        partition_worker_budget=max(
            1,
            min(plan.partition_workers, int(payload.get('partition_worker_budget') or plan.partition_worker_budget)),
        ),
        load_worker_budget=max(
            1,
            min(plan.load_workers, int(payload.get('load_worker_budget') or plan.load_worker_budget)),
        ),
        merge_worker_budget=max(
            1,
            min(plan.merge_workers, int(payload.get('merge_worker_budget') or plan.merge_worker_budget)),
        ),
        scratch_soft_cap_bytes=max(
            1,
            int(payload.get('scratch_soft_cap_bytes') or plan.scratch_soft_cap_bytes),
        ),
    )


def _read_cpu_ticks() -> tuple[int, int]:
    with Path('/proc/stat').open('r', encoding='utf-8') as handle:
        first_line = handle.readline().strip().split()
    values = [int(value) for value in first_line[1:]]
    return sum(values), values[4] if len(values) > 4 else 0


def _read_memory_snapshot() -> tuple[int, int]:
    values: dict[str, int] = {}
    with Path('/proc/meminfo').open('r', encoding='utf-8') as handle:
        for line in handle:
            key, raw_value = line.split(':', 1)
            values[key] = int(raw_value.strip().split()[0]) * 1024
    total_swap = int(values.get('SwapTotal', 0))
    free_swap = int(values.get('SwapFree', 0))
    return int(values.get('MemAvailable', 0)), max(0, total_swap - free_swap)


def _read_device_busy_ms_for_path(path: str | Path) -> int:
    stat_result = os.stat(path)
    dev_path = Path('/sys/dev/block') / f'{os.major(stat_result.st_dev)}:{os.minor(stat_result.st_dev)}' / 'stat'
    if not dev_path.exists():
        return 0
    fields = dev_path.read_text(encoding='utf-8').strip().split()
    return int(fields[9]) if len(fields) > 9 else 0


def _estimate_directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for file_path in path.rglob('*'):
        if file_path.is_file():
            total += file_path.stat().st_size
    return total


def _sample_host_pressure(plan: FullIngestionPlan) -> dict[str, int]:
    now = time.monotonic()
    device_io_ms = _read_device_busy_ms_for_path(plan.scratch_root)
    total_cpu_ticks, total_iowait_ticks = _read_cpu_ticks()
    available_memory_bytes, swap_used_bytes = _read_memory_snapshot()
    scratch_actual_bytes = _estimate_directory_size(Path(plan.run_root))

    previous = _FULL_INGESTION_PRESSURE_STATE.get(plan.run_id)
    device_util_milli_pct = 0
    iowait_milli_pct = 0
    soft_pressure_streak = 0
    hard_pressure_streak = 0
    recovery_streak = 0

    if previous is not None:
        elapsed_seconds = max(0.001, now - previous.sampled_at)
        device_delta_ms = max(0, device_io_ms - previous.device_io_ms)
        cpu_delta_ticks = max(1, total_cpu_ticks - previous.total_cpu_ticks)
        iowait_delta_ticks = max(0, total_iowait_ticks - previous.total_iowait_ticks)
        device_util_milli_pct = int(min(100_000, round((device_delta_ms / (elapsed_seconds * 1000.0)) * 100_000)))
        iowait_milli_pct = int(min(100_000, round((iowait_delta_ticks / cpu_delta_ticks) * 100_000)))
        soft_pressure_streak = previous.soft_pressure_streak
        hard_pressure_streak = previous.hard_pressure_streak
        recovery_streak = previous.recovery_streak

    _FULL_INGESTION_PRESSURE_STATE[plan.run_id] = HostPressureState(
        sampled_at=now,
        device_io_ms=device_io_ms,
        total_cpu_ticks=total_cpu_ticks,
        total_iowait_ticks=total_iowait_ticks,
        soft_pressure_streak=soft_pressure_streak,
        hard_pressure_streak=hard_pressure_streak,
        recovery_streak=recovery_streak,
    )
    return {
        'device_util_milli_pct': device_util_milli_pct,
        'iowait_milli_pct': iowait_milli_pct,
        'available_memory_bytes': available_memory_bytes,
        'swap_used_bytes': swap_used_bytes,
        'scratch_actual_bytes': scratch_actual_bytes,
    }


def apply_full_ingestion_backpressure(plan: FullIngestionPlan) -> FullIngestionPlan:
    control_payload = read_full_ingestion_control(plan)
    policy_mode = _normalize_policy_mode(control_payload.get('policy_mode'))
    requested_partition_budget = max(
        1,
        min(
            plan.partition_workers,
            int(
                control_payload.get('partition_worker_budget_cap')
                or control_payload.get('partition_worker_budget')
                or _default_worker_budget(
                    plan.partition_workers,
                    policy_mode=policy_mode,
                    interactive_cap=8,
                )
            ),
        ),
    )
    requested_load_budget = max(
        1,
        min(
            plan.load_workers,
            int(
                control_payload.get('load_worker_budget_cap')
                or control_payload.get('load_worker_budget')
                or _default_worker_budget(
                    plan.load_workers,
                    policy_mode=policy_mode,
                    interactive_cap=2,
                )
            ),
        ),
    )
    requested_merge_budget = max(
        1,
        min(
            plan.merge_workers,
            int(
                control_payload.get('merge_worker_budget_cap')
                or control_payload.get('merge_worker_budget')
                or _default_worker_budget(
                    plan.merge_workers,
                    policy_mode=policy_mode,
                    interactive_cap=1,
                )
            ),
        ),
    )
    configured_partition_budget = _default_worker_budget(
        plan.partition_workers,
        policy_mode=policy_mode,
        interactive_cap=8,
    )
    configured_load_budget = _default_worker_budget(
        plan.load_workers,
        policy_mode=policy_mode,
        interactive_cap=2,
    )
    configured_merge_budget = _default_worker_budget(
        plan.merge_workers,
        policy_mode=policy_mode,
        interactive_cap=1,
    )
    scratch_soft_cap_bytes = max(
        1,
        int(control_payload.get('scratch_soft_cap_bytes') or plan.scratch_soft_cap_bytes),
    )
    scratch_estimated_bytes = int(plan.counters.get('chunk_bytes_written') or 0) + int(
        plan.counters.get('spool_bytes_estimated') or 0
    )
    host_sample = _sample_host_pressure(plan)

    partition_budget = max(
        1,
        min(
            plan.partition_workers,
            int(control_payload.get('partition_worker_budget') or requested_partition_budget),
        ),
    )
    load_budget = max(
        1,
        min(
            plan.load_workers,
            int(control_payload.get('load_worker_budget') or requested_load_budget),
        ),
    )
    merge_budget = max(
        1,
        min(
            plan.merge_workers,
            int(control_payload.get('merge_worker_budget') or requested_merge_budget),
        ),
    )
    soft_device_util_milli_pct = 75_000 if policy_mode == FULL_INGESTION_POLICY_INTERACTIVE else 85_000
    hard_device_util_milli_pct = 90_000
    soft_iowait_milli_pct = 12_000 if policy_mode == FULL_INGESTION_POLICY_INTERACTIVE else 18_000
    hard_iowait_milli_pct = 20_000
    soft_available_memory_bytes = 16 * 1024 * 1024 * 1024
    hard_available_memory_bytes = 8 * 1024 * 1024 * 1024
    soft_swap_used_bytes = 4 * 1024 * 1024 * 1024 if policy_mode == FULL_INGESTION_POLICY_INTERACTIVE else 8 * 1024 * 1024 * 1024
    hard_swap_used_bytes = 12 * 1024 * 1024 * 1024
    hard_scratch_cap_bytes = max(scratch_soft_cap_bytes + (150 * 1024 * 1024 * 1024), scratch_soft_cap_bytes)

    state = _FULL_INGESTION_PRESSURE_STATE[plan.run_id]
    soft_pressure = (
        scratch_estimated_bytes >= scratch_soft_cap_bytes
        or host_sample['scratch_actual_bytes'] >= scratch_soft_cap_bytes
        or host_sample['device_util_milli_pct'] >= soft_device_util_milli_pct
        or host_sample['iowait_milli_pct'] >= soft_iowait_milli_pct
        or host_sample['available_memory_bytes'] <= soft_available_memory_bytes
        or host_sample['swap_used_bytes'] >= soft_swap_used_bytes
    )
    hard_pressure = (
        scratch_estimated_bytes >= hard_scratch_cap_bytes
        or host_sample['scratch_actual_bytes'] >= hard_scratch_cap_bytes
        or host_sample['device_util_milli_pct'] >= hard_device_util_milli_pct
        or host_sample['iowait_milli_pct'] >= hard_iowait_milli_pct
        or host_sample['available_memory_bytes'] <= hard_available_memory_bytes
        or host_sample['swap_used_bytes'] >= hard_swap_used_bytes
    )

    if hard_pressure:
        state.hard_pressure_streak += 1
        state.soft_pressure_streak = max(state.soft_pressure_streak + 1, 1)
        state.recovery_streak = 0
    elif soft_pressure:
        state.soft_pressure_streak += 1
        state.hard_pressure_streak = 0
        state.recovery_streak = 0
    else:
        state.recovery_streak += 1
        state.soft_pressure_streak = 0
        state.hard_pressure_streak = 0

    if state.hard_pressure_streak >= 2:
        partition_budget = 1
        load_budget = 1
        merge_budget = max(1, min(merge_budget, requested_merge_budget))
    elif state.soft_pressure_streak >= 3:
        partition_budget = max(1, min(partition_budget, max(1, requested_partition_budget // 2)))
        load_budget = max(1, min(load_budget, max(1, requested_load_budget - 1)))
        merge_budget = max(1, min(merge_budget, requested_merge_budget))
    elif state.recovery_streak >= 10:
        partition_budget = min(requested_partition_budget, max(partition_budget, configured_partition_budget))
        load_budget = min(requested_load_budget, max(load_budget, configured_load_budget))
        merge_budget = min(requested_merge_budget, max(merge_budget, configured_merge_budget))

    write_full_ingestion_control(
        plan,
        policy_mode=policy_mode,
        partition_worker_budget=partition_budget,
        load_worker_budget=load_budget,
        merge_worker_budget=merge_budget,
        scratch_soft_cap_bytes=scratch_soft_cap_bytes,
    )
    return replace(
        plan,
        policy_mode=policy_mode,
        partition_worker_budget=partition_budget,
        load_worker_budget=load_budget,
        merge_worker_budget=merge_budget,
        scratch_soft_cap_bytes=scratch_soft_cap_bytes,
        counters={
            **plan.counters,
            'scratch_actual_bytes': host_sample['scratch_actual_bytes'],
            'host_device_util_milli_pct': host_sample['device_util_milli_pct'],
            'host_iowait_milli_pct': host_sample['iowait_milli_pct'],
            'host_available_memory_bytes': host_sample['available_memory_bytes'],
            'host_swap_used_bytes': host_sample['swap_used_bytes'],
        },
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
    write_full_ingestion_control(plan)
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
    plan = sync_full_ingestion_runtime_control(plan)
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

    def _record_copy_result(partition_key: str, result: FullIngestionCopyResult) -> None:
        nonlocal running_plan
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

    try:
        future_to_partition: dict[Any, str] = {}
        partition_iter = iter(pending_partition_keys)
        use_parallel_copy = len(pending_partition_keys) > max(4, plan.load_worker_budget)
        if not use_parallel_copy:
            for partition_key in pending_partition_keys:
                running_plan = apply_full_ingestion_backpressure(running_plan)
                _, result = _load_partition_lane(partition_key)
                _record_copy_result(partition_key, result)
        else:
            with ThreadPoolExecutor(max_workers=max(1, plan.load_workers)) as executor:
                for _ in range(min(max(1, plan.load_worker_budget), len(pending_partition_keys))):
                    partition_key = next(partition_iter, None)
                    if partition_key is None:
                        break
                    future = executor.submit(_load_partition_lane, partition_key)
                    future_to_partition[future] = partition_key

                while future_to_partition:
                    done, _ = wait(future_to_partition.keys(), return_when=FIRST_COMPLETED)
                    for future in done:
                        running_plan = apply_full_ingestion_backpressure(running_plan)
                        partition_key = future_to_partition.pop(future)
                        try:
                            _, result = future.result()
                        except Exception:
                            index = partition_index_by_key[partition_key]
                            finalized_partitions[index] = replace(finalized_partitions[index], state='failed')
                            raise
                        _record_copy_result(partition_key, result)

                        next_partition_key = next(partition_iter, None)
                        if next_partition_key is not None and len(future_to_partition) < max(
                            1,
                            min(plan.load_workers, running_plan.load_worker_budget),
                        ):
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

    finalized_partitions = [
        replace(partition, state='loaded') if partition.state == 'partitioned' else partition
        for partition in finalized_partitions
    ]
    with connection.cursor() as cursor:
        counters['rows_staged'] = _count_load_rows(cursor, LISTENBRAINZ_EVENT_LOAD_TABLE, running_plan.run_id)
        counters['session_rows_loaded'] = _count_load_rows(
            cursor,
            LISTENBRAINZ_SESSION_LOAD_TABLE,
            running_plan.run_id,
        )
    counters['partitions_loaded'] = sum(1 for partition in finalized_partitions if partition.state == 'loaded')
    completed_plan = replace(
        running_plan,
        updated_at=datetime.now(tz=UTC).isoformat(),
        counters=dict(counters),
        partitions=list(finalized_partitions),
    )
    completed_plan = cleanup_full_ingestion_partition_artifacts(completed_plan)
    _persist_full_ingestion_state(completed_plan)
    return completed_plan


def execute_full_ingestion_merge_stage(
    plan: FullIngestionPlan,
    *,
    force: bool = False,
) -> FullIngestionPlan:
    normalized_partitions = [
        replace(partition, state='loaded') if partition.state == 'merging' else partition
        for partition in plan.partitions
    ]
    if any(partition.state not in ('loaded', 'merged') for partition in normalized_partitions):
        raise ValueError('Merge stage requires all partitions to be loaded into lean load tables first.')

    if (
        all(partition.state == 'merged' for partition in normalized_partitions)
        and int(plan.counters.get('swap_completed') or 0) == 1
        and not force
    ):
        return plan

    merge_partitions = list(normalized_partitions)
    if force:
        merge_partitions = [
            replace(partition, state='loaded') if partition.state == 'merged' else partition
            for partition in merge_partitions
        ]

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
            'rows_resolved': 0 if force else int(plan.counters.get('rows_resolved') or 0),
            'rows_unresolved': 0 if force else int(plan.counters.get('rows_unresolved') or 0),
            'partitions_merged': 0 if force else int(plan.counters.get('partitions_merged') or 0),
            'cold_build_complete': 0 if force else int(plan.counters.get('cold_build_complete') or 0),
            'hot_stage_complete': 0 if force else int(plan.counters.get('hot_stage_complete') or 0),
            'hot_build_complete': 0 if force else int(plan.counters.get('hot_build_complete') or 0),
            'shadow_indexes_complete': 0 if force else int(plan.counters.get('shadow_indexes_complete') or 0),
            'swap_completed': 0 if force else int(plan.counters.get('swap_completed') or 0),
        },
        partitions=merge_partitions,
    )
    _persist_full_ingestion_state(running_plan)
    try:
        result, finalized_partitions = provider.finalize_into_final_tables(
            running_plan,
            source_ingestion_run=source_ingestion_run,
            force=force,
        )
    except Exception as exc:
        persisted_plan = load_full_ingestion_plan(Path(running_plan.manifest_path))
        failed_plan = replace(
            persisted_plan,
            status=FULL_INGESTION_STATUS_FAILED,
            updated_at=datetime.now(tz=UTC).isoformat(),
            counters={
                **persisted_plan.counters,
                'partitions_failed': sum(
                    1 for partition in persisted_plan.partitions if partition.state == 'failed'
                ) or persisted_plan.partition_count,
            },
            partitions=[
                replace(partition, state='failed')
                if partition.state not in ('merged', 'failed')
                else partition
                for partition in persisted_plan.partitions
            ],
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
            'partitions_merged': sum(1 for partition in finalized_partitions if partition.state == 'merged'),
            'partitions_failed': 0,
        },
        partitions=finalized_partitions,
    )
    completed_plan = cleanup_full_ingestion_scratch(completed_plan)
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


def cleanup_full_ingestion_partition_artifacts(plan: FullIngestionPlan) -> FullIngestionPlan:
    for partition in plan.partitions:
        events_root = Path(plan.partition_root) / partition.partition_key / 'events'
        if events_root.exists():
            shutil.rmtree(events_root)

    spool_root = Path(plan.run_root) / 'spool'
    if spool_root.exists():
        shutil.rmtree(spool_root)

    return replace(
        plan,
        updated_at=datetime.now(tz=UTC).isoformat(),
        counters={
            **plan.counters,
            'scratch_actual_bytes': _estimate_directory_size(Path(plan.run_root)),
            'spool_bytes_estimated': 0,
        },
    )


def cleanup_full_ingestion_scratch(plan: FullIngestionPlan) -> FullIngestionPlan:
    for path in (
        Path(plan.partition_root),
        Path(plan.run_root) / 'spool',
        Path(plan.log_root),
    ):
        if path.exists():
            shutil.rmtree(path)

    return replace(
        plan,
        updated_at=datetime.now(tz=UTC).isoformat(),
        counters={
            **plan.counters,
            'scratch_actual_bytes': _estimate_directory_size(Path(plan.run_root)),
        },
    )


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
    scratch_estimated_bytes = int(plan.counters.get('chunk_bytes_written') or 0) + int(
        plan.counters.get('spool_bytes_estimated') or 0
    )

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
            f'stage="{_escape_label(plan.stage)}",'
            f'policy="{_escape_label(plan.policy_mode)}"'
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
            '# HELP mlcore_full_ingestion_worker_budget Active worker budgets by role.',
            '# TYPE mlcore_full_ingestion_worker_budget gauge',
            (
                'mlcore_full_ingestion_worker_budget{'
                f'provider="{_escape_label(plan.provider)}",'
                f'run_id="{_escape_label(plan.run_id)}",'
                'role="partition"'
                '} '
                f'{plan.partition_worker_budget}'
            ),
            (
                'mlcore_full_ingestion_worker_budget{'
                f'provider="{_escape_label(plan.provider)}",'
                f'run_id="{_escape_label(plan.run_id)}",'
                'role="load"'
                '} '
                f'{plan.load_worker_budget}'
            ),
            (
                'mlcore_full_ingestion_worker_budget{'
                f'provider="{_escape_label(plan.provider)}",'
                f'run_id="{_escape_label(plan.run_id)}",'
                'role="merge"'
                '} '
                f'{plan.merge_worker_budget}'
            ),
            '# HELP mlcore_full_ingestion_scratch_soft_cap_bytes Active soft cap for estimated scratch usage.',
            '# TYPE mlcore_full_ingestion_scratch_soft_cap_bytes gauge',
            (
                'mlcore_full_ingestion_scratch_soft_cap_bytes{'
                f'provider="{_escape_label(plan.provider)}",'
                f'run_id="{_escape_label(plan.run_id)}"'
                '} '
                f'{plan.scratch_soft_cap_bytes}'
            ),
            '# HELP mlcore_full_ingestion_scratch_estimated_bytes Estimated active scratch bytes for the run.',
            '# TYPE mlcore_full_ingestion_scratch_estimated_bytes gauge',
            (
                'mlcore_full_ingestion_scratch_estimated_bytes{'
                f'provider="{_escape_label(plan.provider)}",'
                f'run_id="{_escape_label(plan.run_id)}"'
                '} '
                f'{scratch_estimated_bytes}'
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

    def resolve(self, parsed_payload: Any) -> ListenBrainzIdentityResolution:
        spotify_id = str(parsed_payload.track_identifier_candidates.get('spotify_id') or '').strip()
        identity = identity_from_listenbrainz_candidates(
            recording_mbid=str(parsed_payload.recording_mbid or ''),
            spotify_id=spotify_id,
            recording_msid=parsed_payload.recording_msid,
        )
        if identity is None:
            return ListenBrainzIdentityResolution(
                canonical_item_id='',
                canonical_item_type='',
                canonical_item_key='',
                track_id='',
                candidate_type='none',
                resolution_type='',
            )

        track_id = ''
        if identity.item_type == 'recording_mbid':
            track_id = self.mbid_to_track_id.get(str(parsed_payload.recording_mbid), '')
        elif identity.item_type == 'spotify_track':
            track_id = self.spotify_to_track_id.get(spotify_id, '')

        return ListenBrainzIdentityResolution(
            canonical_item_id=str(identity.item_id),
            canonical_item_type=identity.item_type,
            canonical_item_key=identity.canonical_key,
            track_id=track_id,
            candidate_type=identity.item_type,
            resolution_type=identity.item_type,
        )


@dataclass(frozen=True)
class ListenBrainzIdentityResolution:
    canonical_item_id: str
    canonical_item_type: str
    canonical_item_key: str
    track_id: str
    candidate_type: str
    resolution_type: str


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
    canonical_item_id: str,
    event_signature: bytes,
    partition_count: int,
) -> int:
    digest = hashlib.sha256()
    digest.update(session_key)
    if canonical_item_id:
        digest.update(canonical_item_id.encode('utf-8'))
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
        'rows_with_mbid_candidate': 0,
        'rows_with_spotify_candidate': 0,
        'rows_with_no_candidate': 0,
        'rows_resolved': 0,
        'rows_resolved_by_mbid': 0,
        'rows_resolved_by_spotify': 0,
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
            resolution = identity_snapshot.resolve(parsed)
            canonical_item_id = resolution.canonical_item_id
            track_id = resolution.track_id
            if resolution.candidate_type == 'recording_mbid':
                counters['rows_with_mbid_candidate'] += 1
            elif resolution.candidate_type == 'spotify_track':
                counters['rows_with_spotify_candidate'] += 1
            else:
                counters['rows_with_no_candidate'] += 1
            if canonical_item_id:
                counters['rows_resolved'] += 1
                if resolution.resolution_type == 'recording_mbid':
                    counters['rows_resolved_by_mbid'] += 1
                elif resolution.resolution_type == 'spotify_track':
                    counters['rows_resolved_by_spotify'] += 1
            else:
                counters['rows_unresolved'] += 1
            partition_index = partition_index_for_event(
                parsed.session_key,
                canonical_item_id=canonical_item_id,
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
                    canonical_item_id or r'\N',
                    resolution.canonical_item_type or r'\N',
                    resolution.canonical_item_key or r'\N',
                    track_id or r'\N',
                    '1' if canonical_item_id else '0',
                    f'{origin}:{line_number}:{entry_index}',
                ]
            )

    chunk_manifests_by_partition: dict[str, list[dict[str, int | str]]] = {}
    for partition_key, writer in writers.items():
        chunk_manifests_by_partition[partition_key] = writer.finish()

    return ListenBrainzMemberChunkResult(
        member_token=member_token,
        spool_size_bytes=Path(spool_path).stat().st_size,
        counters=counters,
        chunk_manifests_by_partition=chunk_manifests_by_partition,
    )


def extract_listenbrainz_archive(plan: FullIngestionPlan) -> FullIngestionPlan:
    plan = sync_full_ingestion_runtime_control(plan)
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
    use_process_pool = max_in_flight > 1 and plan.archive_size_bytes >= 64 * 1024 * 1024
    close_old_connections()
    host_counter_keys = (
        'scratch_actual_bytes',
        'host_device_util_milli_pct',
        'host_iowait_milli_pct',
        'host_available_memory_bytes',
        'host_swap_used_bytes',
    )

    def _record_member_result(result: ListenBrainzMemberChunkResult) -> None:
        nonlocal counters, running_plan
        running_plan = apply_full_ingestion_backpressure(running_plan)
        counters['rows_parsed'] = int(counters.get('rows_parsed') or 0) + int(result.counters['rows_parsed'])
        counters['rows_with_mbid_candidate'] = int(counters.get('rows_with_mbid_candidate') or 0) + int(
            result.counters['rows_with_mbid_candidate']
        )
        counters['rows_with_spotify_candidate'] = int(counters.get('rows_with_spotify_candidate') or 0) + int(
            result.counters['rows_with_spotify_candidate']
        )
        counters['rows_with_no_candidate'] = int(counters.get('rows_with_no_candidate') or 0) + int(
            result.counters['rows_with_no_candidate']
        )
        counters['rows_resolved'] = int(counters.get('rows_resolved') or 0) + int(result.counters['rows_resolved'])
        counters['rows_resolved_by_mbid'] = int(counters.get('rows_resolved_by_mbid') or 0) + int(
            result.counters['rows_resolved_by_mbid']
        )
        counters['rows_resolved_by_spotify'] = int(counters.get('rows_resolved_by_spotify') or 0) + int(
            result.counters['rows_resolved_by_spotify']
        )
        counters['rows_unresolved'] = int(counters.get('rows_unresolved') or 0) + int(result.counters['rows_unresolved'])
        counters['rows_malformed'] = int(counters.get('rows_malformed') or 0) + int(result.counters['rows_malformed'])
        counters['spool_bytes_estimated'] = max(
            0,
            int(counters.get('spool_bytes_estimated') or 0) - int(result.spool_size_bytes),
        )
        counters['spooled_members_in_flight'] = max(
            0,
            int(counters.get('spooled_members_in_flight') or 0) - 1,
        )
        for partition_key, chunk_manifests in result.chunk_manifests_by_partition.items():
            partition_chunk_manifests[partition_key].extend(chunk_manifests)
            counters['chunks_written'] = int(counters.get('chunks_written') or 0) + len(chunk_manifests)
            counters['chunk_bytes_written'] = int(counters.get('chunk_bytes_written') or 0) + sum(
                int(chunk_manifest.get('size_bytes') or 0) for chunk_manifest in chunk_manifests
            )
        spool_path = spool_root / f'{result.member_token}.listens'
        if spool_path.exists():
            spool_path.unlink()
        for key in host_counter_keys:
            counters[key] = int(running_plan.counters.get(key) or counters.get(key) or 0)
        running_plan = replace(
            running_plan,
            counters=dict(counters),
            updated_at=datetime.now(tz=UTC).isoformat(),
        )
        _persist_full_ingestion_state(running_plan)

    with tarfile.open(Path(plan.archive_path), 'r:*') as archive:
        if not use_process_pool:
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
                spool_size_bytes = spool_path.stat().st_size
                counters['spool_bytes_estimated'] = int(counters.get('spool_bytes_estimated') or 0) + spool_size_bytes
                counters['spooled_members_in_flight'] = int(counters.get('spooled_members_in_flight') or 0) + 1
                _record_member_result(
                    _process_listenbrainz_spooled_member(
                        spool_path=str(spool_path),
                        origin=relative_path.as_posix(),
                        member_token=member_token,
                        partition_root=plan.partition_root,
                        run_id=plan.run_id,
                        partition_count=plan.partition_count,
                        chunk_target_rows=chunk_target_rows,
                        identity_snapshot=identity_snapshot,
                    )
                )
        else:
            with ProcessPoolExecutor(
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
                    spool_size_bytes = spool_path.stat().st_size
                    counters['spool_bytes_estimated'] = int(counters.get('spool_bytes_estimated') or 0) + spool_size_bytes
                    counters['spooled_members_in_flight'] = int(counters.get('spooled_members_in_flight') or 0) + 1

                    future = executor.submit(
                        _process_listenbrainz_spooled_member_in_worker,
                        spool_path=str(spool_path),
                        origin=relative_path.as_posix(),
                        member_token=member_token,
                    )
                    future_to_member[future] = member_token

                    while len(future_to_member) >= max(
                        1,
                        min(max_in_flight, running_plan.partition_worker_budget),
                    ):
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
    expected_event_columns = [
        'run_id',
        'partition_key',
        'event_signature',
        'played_at',
        'session_key',
        'canonical_item_id',
        'canonical_item_type',
        'canonical_item_key',
        'track_id',
        'resolution_state',
        'cold_ref',
    ]
    expected_session_columns = [
        'run_id',
        'partition_key',
        'session_key',
        'canonical_item_id',
        'track_id',
        'first_played_at',
        'last_played_at',
        'play_count',
    ]
    expected_stage_columns = [
        'run_id',
        'partition_key',
        'session_key',
        'canonical_item_id',
        'track_id',
        'first_played_at',
        'last_played_at',
        'play_count',
    ]
    expected_checkpoint_columns = [
        'run_id',
        'phase',
        'partition_key',
        'completed_at',
    ]

    def _table_columns(table_name: str) -> list[str]:
        with connection.cursor() as cursor:
            if connection.vendor == 'postgresql':
                cursor.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = current_schema()
                      AND table_name = %s
                    ORDER BY ordinal_position
                    """,
                    [table_name],
                )
                return [str(row[0]) for row in cursor.fetchall()]

            cursor.execute(f"PRAGMA table_info('{table_name}')")
            return [str(row[1]) for row in cursor.fetchall()]

    def _drop_table_if_mismatched(table_name: str, expected_columns: list[str]) -> None:
        actual_columns = _table_columns(table_name)
        if actual_columns and actual_columns != expected_columns:
            with connection.cursor() as cursor:
                cursor.execute(f'DROP TABLE IF EXISTS {table_name}')

    def _reconcile_session_stage_table() -> None:
        actual_columns = _table_columns(LISTENBRAINZ_SESSION_STAGE_TABLE)
        legacy_columns = [
            'run_id',
            'session_key',
            'canonical_item_id',
            'track_id',
            'first_played_at',
            'last_played_at',
            'play_count',
        ]
        if not actual_columns or actual_columns == expected_stage_columns:
            return
        if actual_columns == legacy_columns:
            with connection.cursor() as cursor:
                if connection.vendor == 'postgresql':
                    cursor.execute(
                        f'''
                        ALTER TABLE {LISTENBRAINZ_SESSION_STAGE_TABLE}
                        ADD COLUMN partition_key varchar(16) NOT NULL DEFAULT ''
                        '''
                    )
                else:
                    cursor.execute(
                        f'''
                        ALTER TABLE {LISTENBRAINZ_SESSION_STAGE_TABLE}
                        ADD COLUMN partition_key text NOT NULL DEFAULT ''
                        '''
                    )
                    cursor.execute(
                        f'''
                        UPDATE {LISTENBRAINZ_SESSION_STAGE_TABLE}
                        SET partition_key = ''
                        WHERE partition_key IS NULL
                        '''
                    )
            return
        with connection.cursor() as cursor:
            cursor.execute(f'DROP TABLE IF EXISTS {LISTENBRAINZ_SESSION_STAGE_TABLE}')

    _drop_table_if_mismatched(LISTENBRAINZ_EVENT_LOAD_TABLE, expected_event_columns)
    _drop_table_if_mismatched(LISTENBRAINZ_SESSION_LOAD_TABLE, expected_session_columns)
    _reconcile_session_stage_table()
    _drop_table_if_mismatched(LISTENBRAINZ_FINALIZE_CHECKPOINT_TABLE, expected_checkpoint_columns)

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
                    canonical_item_id uuid NULL,
                    canonical_item_type varchar(32) NULL,
                    canonical_item_key varchar(512) NULL,
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
                    canonical_item_id uuid NOT NULL,
                    track_id uuid NULL,
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
            cursor.execute(
                f'''
                CREATE UNLOGGED TABLE IF NOT EXISTS {LISTENBRAINZ_SESSION_STAGE_TABLE} (
                    run_id uuid NOT NULL,
                    partition_key varchar(16) NOT NULL,
                    session_key bytea NOT NULL,
                    canonical_item_id uuid NOT NULL,
                    track_id uuid NULL,
                    first_played_at timestamptz NOT NULL,
                    last_played_at timestamptz NOT NULL,
                    play_count integer NOT NULL
                )
                '''
            )
            cursor.execute(
                f'''
                CREATE INDEX IF NOT EXISTS {LISTENBRAINZ_SESSION_STAGE_TABLE}_run_partition_idx
                ON {LISTENBRAINZ_SESSION_STAGE_TABLE} (run_id, partition_key)
                '''
            )
            cursor.execute(
                f'''
                CREATE TABLE IF NOT EXISTS {LISTENBRAINZ_FINALIZE_CHECKPOINT_TABLE} (
                    run_id uuid NOT NULL,
                    phase varchar(64) NOT NULL,
                    partition_key varchar(16) NOT NULL,
                    completed_at timestamptz NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (run_id, phase, partition_key)
                )
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
                    canonical_item_id text NULL,
                    canonical_item_type text NULL,
                    canonical_item_key text NULL,
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
                    canonical_item_id text NOT NULL,
                    track_id text NULL,
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
            cursor.execute(
                f'''
                CREATE TABLE IF NOT EXISTS {LISTENBRAINZ_SESSION_STAGE_TABLE} (
                    run_id text NOT NULL,
                    partition_key text NOT NULL,
                    session_key blob NOT NULL,
                    canonical_item_id text NOT NULL,
                    track_id text NULL,
                    first_played_at text NOT NULL,
                    last_played_at text NOT NULL,
                    play_count integer NOT NULL
                )
                '''
            )
            cursor.execute(
                f'''
                CREATE INDEX IF NOT EXISTS {LISTENBRAINZ_SESSION_STAGE_TABLE}_run_partition_idx
                ON {LISTENBRAINZ_SESSION_STAGE_TABLE} (run_id, partition_key)
                '''
            )
            cursor.execute(
                f'''
                CREATE TABLE IF NOT EXISTS {LISTENBRAINZ_FINALIZE_CHECKPOINT_TABLE} (
                    run_id text NOT NULL,
                    phase text NOT NULL,
                    partition_key text NOT NULL,
                    completed_at text NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (run_id, phase, partition_key)
                )
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
                'canonical_item_id',
                'canonical_item_type',
                'canonical_item_key',
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
                canonical_item_id,
                track_id,
                first_played_at,
                last_played_at,
                play_count
            )
            SELECT
                run_id,
                partition_key,
                session_key,
                canonical_item_id,
                track_id,
                MIN(played_at),
                MAX(played_at),
                COUNT(*)
            FROM {LISTENBRAINZ_EVENT_LOAD_TABLE}
            WHERE run_id = %s
              AND partition_key = %s
              AND canonical_item_id IS NOT NULL
            GROUP BY run_id, partition_key, session_key, canonical_item_id, track_id
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
    force: bool = False,
) -> tuple[FullIngestionMergeResult, list[FullIngestionPartitionPlan]]:
    if connection.vendor != 'postgresql':
        result = finalize_listenbrainz_full_ingestion_direct(
            plan,
            source_ingestion_run=source_ingestion_run,
        )
        return result, [replace(partition, state='merged') for partition in plan.partitions]

    ensure_listenbrainz_load_tables()
    with connection.cursor() as cursor:
        if force:
            _clear_finalize_checkpoints(cursor, plan.run_id)
            _drop_listenbrainz_shadow_tables(cursor)
        if not _relation_exists(cursor, LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE):
            _create_empty_listenbrainz_event_ledger_build_table(cursor)
        if not _relation_exists(cursor, LISTENBRAINZ_SESSION_STAGE_TABLE):
            _ensure_listenbrainz_session_stage_table(cursor)
        if not _relation_exists(cursor, LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE):
            _create_empty_listenbrainz_session_track_build_table(cursor)

        drained_partition_keys = _load_finalize_checkpointed_partitions(
            cursor,
            run_id=plan.run_id,
            phase=LISTENBRAINZ_FINALIZE_PHASE_PARTITION_DRAIN,
        )
        hot_built_partition_keys = _load_finalize_checkpointed_partitions(
            cursor,
            run_id=plan.run_id,
            phase=LISTENBRAINZ_FINALIZE_PHASE_HOT_BUILD,
        )
        shadow_indexes_complete = _finalize_phase_completed(
            cursor,
            run_id=plan.run_id,
            phase=LISTENBRAINZ_FINALIZE_PHASE_SHADOW_INDEXES,
        )
        swap_completed = _finalize_phase_completed(
            cursor,
            run_id=plan.run_id,
            phase=LISTENBRAINZ_FINALIZE_PHASE_SWAP,
        )
        current_rows_merged = _count_table_rows(cursor, LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE)
        current_rows_resolved = _count_table_rows(
            cursor,
            LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE,
            where_clause='canonical_item_id IS NOT NULL',
        )
        current_rows_unresolved = _count_table_rows(
            cursor,
            LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE,
            where_clause='canonical_item_id IS NULL',
        )
        current_session_rows = _count_table_rows(cursor, LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE)

    counters = dict(plan.counters)
    counters['rows_merged'] = int(current_rows_merged)
    counters['rows_resolved'] = int(current_rows_resolved)
    counters['rows_unresolved'] = int(current_rows_unresolved)
    counters['partitions_merged'] = len(drained_partition_keys)
    counters['cold_build_complete'] = 1 if len(drained_partition_keys) == len(plan.partitions) else 0
    counters['hot_stage_complete'] = 1 if len(drained_partition_keys) == len(plan.partitions) else 0
    counters['hot_build_partitions_completed'] = len(hot_built_partition_keys)
    counters['hot_build_complete'] = 1 if len(hot_built_partition_keys) == len(plan.partitions) else 0
    counters['shadow_indexes_complete'] = 1 if shadow_indexes_complete else 0
    counters['swap_completed'] = 1 if swap_completed else 0
    counters['session_rows_loaded'] = int(current_session_rows)

    finalized_partitions: list[FullIngestionPartitionPlan] = []
    for partition in plan.partitions:
        if partition.partition_key in drained_partition_keys:
            finalized_partitions.append(replace(partition, state='merged'))
        else:
            finalized_partitions.append(partition)
    partition_index_by_key = {partition.partition_key: index for index, partition in enumerate(finalized_partitions)}
    running_plan = replace(
        plan,
        updated_at=datetime.now(tz=UTC).isoformat(),
        counters=dict(counters),
        partitions=list(finalized_partitions),
    )
    _persist_full_ingestion_state(running_plan)

    def _compute_finalize_lane_budgets(
        total_budget: int,
        *,
        pending_drain_count: int,
        pending_hot_count: int,
    ) -> tuple[int, int]:
        if total_budget <= 1:
            if pending_hot_count > 0 and pending_drain_count == 0:
                return 0, 1
            return 1 if pending_drain_count > 0 else 0, 0

        drain_budget = 0
        hot_budget = 0
        if pending_drain_count > 0:
            drain_budget = 1
        if pending_hot_count > 0:
            hot_budget = 1
        remaining = max(0, total_budget - drain_budget - hot_budget)
        while remaining > 0:
            drain_backlog = max(0, pending_drain_count - drain_budget)
            hot_backlog = max(0, pending_hot_count - hot_budget)
            if hot_backlog >= drain_backlog and pending_hot_count > 0:
                hot_budget += 1
            elif pending_drain_count > 0:
                drain_budget += 1
            elif pending_hot_count > 0:
                hot_budget += 1
            remaining -= 1
        return drain_budget, hot_budget

    def _merge_partition_lane(partition_key: str) -> tuple[str, FullIngestionMergeResult]:
        close_old_connections()
        try:
            result = _finalize_listenbrainz_partition_into_build_tables(
                run_id=running_plan.run_id,
                partition_key=partition_key,
                import_run_id=str(source_ingestion_run.pk),
            )
            return partition_key, result
        finally:
            close_old_connections()

    def _record_merge_result(partition_key: str, partition_result: FullIngestionMergeResult) -> None:
        nonlocal running_plan
        index = partition_index_by_key[partition_key]
        drained_partition_keys.add(partition_key)
        counters['rows_merged'] = int(counters.get('rows_merged') or 0) + partition_result.rows_merged
        counters['rows_deduplicated'] = int(counters.get('rows_deduplicated') or 0) + partition_result.rows_deduplicated
        counters['rows_resolved'] = int(counters.get('rows_resolved') or 0) + partition_result.rows_resolved
        counters['rows_unresolved'] = int(counters.get('rows_unresolved') or 0) + partition_result.rows_unresolved
        counters['partitions_merged'] = len(drained_partition_keys)
        counters['cold_build_complete'] = 1 if len(drained_partition_keys) == len(finalized_partitions) else 0
        counters['hot_stage_complete'] = counters['cold_build_complete']
        finalized_partitions[index] = replace(finalized_partitions[index], state='merged')
        write_full_ingestion_merge_manifest(
            running_plan,
            partition=finalized_partitions[index],
            result=partition_result,
        )
        running_plan = replace(
            running_plan,
            updated_at=datetime.now(tz=UTC).isoformat(),
            counters=dict(counters),
            partitions=list(finalized_partitions),
        )
        _persist_full_ingestion_state(running_plan)

    pending_partition_keys = [
        partition.partition_key
        for partition in finalized_partitions
        if partition.partition_key not in drained_partition_keys
    ]

    def _build_hot_partition_lane(partition_key: str) -> tuple[str, int]:
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                inserted_rows = _materialize_listenbrainz_session_stage_partition_into_build(
                    cursor,
                    run_id=running_plan.run_id,
                    partition_key=partition_key,
                    import_run_id=str(source_ingestion_run.pk),
                )
            return partition_key, inserted_rows
        finally:
            close_old_connections()

    def _record_hot_build_result(partition_key: str, inserted_rows: int) -> None:
        nonlocal running_plan
        hot_built_partition_keys.add(partition_key)
        counters['session_rows_loaded'] = int(counters.get('session_rows_loaded') or 0) + inserted_rows
        counters['hot_build_partitions_completed'] = len(hot_built_partition_keys)
        running_plan = replace(
            running_plan,
            updated_at=datetime.now(tz=UTC).isoformat(),
            counters=dict(counters),
            partitions=list(finalized_partitions),
        )
        _persist_full_ingestion_state(running_plan)

    with connection.cursor() as cursor:
        hot_built_partition_keys = _load_finalize_checkpointed_partitions(
            cursor,
            run_id=plan.run_id,
            phase=LISTENBRAINZ_FINALIZE_PHASE_HOT_BUILD,
        )
        legacy_hot_build_complete = _finalize_phase_completed(
            cursor,
            run_id=plan.run_id,
            phase=LISTENBRAINZ_FINALIZE_PHASE_HOT_BUILD_LEGACY,
        )

    pending_hot_build_keys = [
        partition.partition_key
        for partition in finalized_partitions
        if partition.partition_key not in hot_built_partition_keys
    ]
    queued_hot_build_keys = set(pending_hot_build_keys)
    pending_partition_queue = list(pending_partition_keys)
    pending_hot_build_queue = list(pending_hot_build_keys)
    active_drain_futures: dict[Any, str] = {}
    active_hot_build_futures: dict[Any, str] = {}
    state_lock = threading.Lock()

    def _submit_drain_work(executor: ThreadPoolExecutor, drain_capacity: int) -> None:
        nonlocal running_plan
        while pending_partition_queue and len(active_drain_futures) < drain_capacity:
            partition_key = pending_partition_queue.pop(0)
            index = partition_index_by_key[partition_key]
            finalized_partitions[index] = replace(finalized_partitions[index], state='merging')
            future = executor.submit(_merge_partition_lane, partition_key)
            active_drain_futures[future] = partition_key
        running_plan = replace(
            running_plan,
            updated_at=datetime.now(tz=UTC).isoformat(),
            partitions=list(finalized_partitions),
        )
        _persist_full_ingestion_state(running_plan)

    def _submit_hot_build_work(executor: ThreadPoolExecutor, hot_build_capacity: int) -> None:
        while pending_hot_build_queue and len(active_hot_build_futures) < hot_build_capacity:
            partition_key = pending_hot_build_queue.pop(0)
            future = executor.submit(_build_hot_partition_lane, partition_key)
            active_hot_build_futures[future] = partition_key

    if pending_partition_queue or pending_hot_build_queue:
        max_drain_workers = max(1, plan.merge_workers)
        max_hot_build_workers = max(1, plan.merge_workers)
        with ThreadPoolExecutor(max_workers=max_drain_workers) as drain_executor, ThreadPoolExecutor(
            max_workers=max_hot_build_workers
        ) as hot_build_executor:
            while (
                pending_partition_queue
                or pending_hot_build_queue
                or active_drain_futures
                or active_hot_build_futures
            ):
                with state_lock:
                    running_plan = apply_full_ingestion_backpressure(running_plan)
                    drain_capacity, hot_build_capacity = _compute_finalize_lane_budgets(
                        max(1, running_plan.merge_worker_budget),
                        pending_drain_count=len(pending_partition_queue) + len(active_drain_futures),
                        pending_hot_count=len(pending_hot_build_queue) + len(active_hot_build_futures),
                    )
                    _submit_drain_work(drain_executor, drain_capacity)
                    _submit_hot_build_work(hot_build_executor, hot_build_capacity)
                    wait_targets = [*active_drain_futures.keys(), *active_hot_build_futures.keys()]
                if not wait_targets:
                    continue
                done, _ = wait(wait_targets, return_when=FIRST_COMPLETED)
                for future in done:
                    if future in active_drain_futures:
                        partition_key = active_drain_futures.pop(future)
                        index = partition_index_by_key[partition_key]
                        try:
                            _, partition_result = future.result()
                        except Exception:
                            finalized_partitions[index] = replace(finalized_partitions[index], state='failed')
                            raise
                        with state_lock:
                            _record_merge_result(partition_key, partition_result)
                            if partition_key not in hot_built_partition_keys and partition_key not in queued_hot_build_keys:
                                pending_hot_build_queue.append(partition_key)
                                queued_hot_build_keys.add(partition_key)
                    elif future in active_hot_build_futures:
                        partition_key = active_hot_build_futures.pop(future)
                        try:
                            _, inserted_rows = future.result()
                        except Exception:
                            raise
                        with state_lock:
                            _record_hot_build_result(partition_key, inserted_rows)
                            queued_hot_build_keys.discard(partition_key)

    counters['cold_build_complete'] = 1
    counters['hot_stage_complete'] = 1
    running_plan = replace(
        running_plan,
        updated_at=datetime.now(tz=UTC).isoformat(),
        counters=dict(counters),
        partitions=list(finalized_partitions),
    )
    _persist_full_ingestion_state(running_plan)

    with connection.cursor() as cursor:
        if not legacy_hot_build_complete:
            cursor.execute(
                f'''
                SELECT COUNT(*)
                FROM {LISTENBRAINZ_SESSION_STAGE_TABLE}
                WHERE run_id = %s
                  AND COALESCE(partition_key, '') = %s
                ''',
                [plan.run_id, ''],
            )
            legacy_stage_rows = int(cursor.fetchone()[0] or 0)
            if legacy_stage_rows > 0:
                counters['session_rows_loaded'] = int(counters.get('session_rows_loaded') or 0) + (
                    _materialize_listenbrainz_session_stage_partition_into_build(
                        cursor,
                        run_id=running_plan.run_id,
                        partition_key='',
                        import_run_id=str(source_ingestion_run.pk),
                    )
                )
            _mark_finalize_checkpoint(
                cursor,
                run_id=plan.run_id,
                phase=LISTENBRAINZ_FINALIZE_PHASE_HOT_BUILD_LEGACY,
            )
        if not hot_built_partition_keys and not _finalize_phase_completed(
            cursor,
            run_id=plan.run_id,
            phase=LISTENBRAINZ_FINALIZE_PHASE_HOT_BUILD,
        ):
            cursor.execute(
                f'DELETE FROM {LISTENBRAINZ_SESSION_STAGE_TABLE} WHERE run_id = %s',
                [plan.run_id],
            )
        if not _finalize_phase_completed(cursor, run_id=plan.run_id, phase=LISTENBRAINZ_FINALIZE_PHASE_HOT_BUILD):
            _mark_finalize_checkpoint(cursor, run_id=plan.run_id, phase=LISTENBRAINZ_FINALIZE_PHASE_HOT_BUILD)
        counters['hot_build_complete'] = 1
        counters['hot_build_partitions_completed'] = len(finalized_partitions)
        counters['session_rows_loaded'] = _count_table_rows(cursor, LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE)
        running_plan = replace(
            running_plan,
            updated_at=datetime.now(tz=UTC).isoformat(),
            counters=dict(counters),
            partitions=list(finalized_partitions),
        )
        _persist_full_ingestion_state(running_plan)

        if not _finalize_phase_completed(cursor, run_id=plan.run_id, phase=LISTENBRAINZ_FINALIZE_PHASE_SHADOW_INDEXES):
            _create_listenbrainz_shadow_constraints_and_indexes(cursor)
            _mark_finalize_checkpoint(cursor, run_id=plan.run_id, phase=LISTENBRAINZ_FINALIZE_PHASE_SHADOW_INDEXES)
            counters['shadow_indexes_complete'] = 1
            running_plan = replace(
                running_plan,
                updated_at=datetime.now(tz=UTC).isoformat(),
                counters=dict(counters),
                partitions=list(finalized_partitions),
            )
            _persist_full_ingestion_state(running_plan)

        if not _finalize_phase_completed(cursor, run_id=plan.run_id, phase=LISTENBRAINZ_FINALIZE_PHASE_SWAP):
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
            _mark_finalize_checkpoint(cursor, run_id=plan.run_id, phase=LISTENBRAINZ_FINALIZE_PHASE_SWAP)
            counters['swap_completed'] = 1

        staged_rows = int(plan.counters.get('rows_staged') or 0)
        if counters['swap_completed']:
            inserted_rows = _count_table_rows(cursor, LISTENBRAINZ_EVENT_LEDGER_TABLE)
            resolved_rows = _count_table_rows(
                cursor,
                LISTENBRAINZ_EVENT_LEDGER_TABLE,
                where_clause='canonical_item_id IS NOT NULL',
            )
            unresolved_rows = _count_table_rows(
                cursor,
                LISTENBRAINZ_EVENT_LEDGER_TABLE,
                where_clause='canonical_item_id IS NULL',
            )
            session_rows_merged = _count_table_rows(cursor, LISTENBRAINZ_SESSION_TRACK_TABLE)
        else:
            inserted_rows = _count_table_rows(cursor, LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE)
            resolved_rows = _count_table_rows(
                cursor,
                LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE,
                where_clause='canonical_item_id IS NOT NULL',
            )
            unresolved_rows = _count_table_rows(
                cursor,
                LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE,
                where_clause='canonical_item_id IS NULL',
            )
            session_rows_merged = _count_table_rows(cursor, LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE)

        merge_totals = FullIngestionMergeResult(
            rows_merged=int(inserted_rows),
            rows_deduplicated=max(0, staged_rows - int(inserted_rows)),
            rows_resolved=int(resolved_rows),
            rows_unresolved=int(unresolved_rows),
            session_rows_merged=int(session_rows_merged),
        )
    counters['rows_merged'] = merge_totals.rows_merged
    counters['rows_deduplicated'] = merge_totals.rows_deduplicated
    counters['rows_resolved'] = merge_totals.rows_resolved
    counters['rows_unresolved'] = merge_totals.rows_unresolved
    counters['session_rows_loaded'] = merge_totals.session_rows_merged
    counters['partitions_merged'] = len(finalized_partitions)
    counters['cold_build_complete'] = 1
    counters['hot_stage_complete'] = 1
    counters['hot_build_complete'] = 1
    counters['hot_build_partitions_completed'] = len(finalized_partitions)
    counters['shadow_indexes_complete'] = 1
    counters['swap_completed'] = 1
    running_plan = replace(
        running_plan,
        updated_at=datetime.now(tz=UTC).isoformat(),
        counters=dict(counters),
        partitions=list(finalized_partitions),
    )
    _persist_full_ingestion_state(running_plan)
    return merge_totals, finalized_partitions


def finalize_listenbrainz_full_ingestion_direct(
    plan: FullIngestionPlan,
    *,
    source_ingestion_run: SourceIngestionRun,
) -> FullIngestionMergeResult:
    with connection.cursor() as cursor:
        _upsert_canonical_items_from_load_table(cursor, plan.run_id)
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
                    canonical_item_id,
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
                    canonical_item_id,
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
                    canonical_item_id,
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
                    deduplicated_events.canonical_item_id,
                    deduplicated_events.track_id,
                    deduplicated_events.resolution_state,
                    deduplicated_events.cold_ref,
                    NOW()
                FROM deduplicated_events
                ON CONFLICT (event_signature) DO NOTHING
                RETURNING canonical_item_id
            ),
            upserted_session_tracks AS (
                INSERT INTO {LISTENBRAINZ_SESSION_TRACK_TABLE} (
                    id,
                    import_run_id,
                    session_key,
                    canonical_item_id,
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
                            "session_delta.canonical_item_id::text"
                        )
                    },
                    %s,
                    session_delta.session_key,
                    session_delta.canonical_item_id,
                    session_delta.track_id,
                    session_delta.first_played_at,
                    session_delta.last_played_at,
                    session_delta.play_count,
                    NOW()
                FROM {LISTENBRAINZ_SESSION_LOAD_TABLE} session_delta
                WHERE session_delta.run_id = %s
                ON CONFLICT (session_key, canonical_item_id) DO UPDATE
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
                COALESCE((SELECT COUNT(*) FROM inserted_events WHERE canonical_item_id IS NOT NULL), 0) AS resolved_rows,
                COALESCE((SELECT COUNT(*) FROM inserted_events WHERE canonical_item_id IS NULL), 0) AS unresolved_rows,
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


def _count_partition_rows(cursor, table_name: str, run_id: str, partition_key: str) -> int:
    cursor.execute(
        f'SELECT COUNT(*) FROM {table_name} WHERE run_id = %s AND partition_key = %s',
        [run_id, partition_key],
    )
    return int(cursor.fetchone()[0] or 0)


def _materialize_listenbrainz_session_stage_partition_into_build(
    cursor,
    *,
    run_id: str,
    partition_key: str,
    import_run_id: str,
) -> int:
    with transaction.atomic():
        cursor.execute(
            f'''
            WITH inserted_session_rows AS (
                INSERT INTO {LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE} (
                    id,
                    import_run_id,
                    session_key,
                    canonical_item_id,
                    track_id,
                    first_played_at,
                    last_played_at,
                    play_count,
                    created_at
                )
                SELECT
                    {
                        deterministic_uuid_sql(
                            "encode(session_stage.session_key, 'hex') || ':' || "
                            "session_stage.canonical_item_id::text"
                        )
                    },
                    %s::uuid,
                    session_stage.session_key,
                    session_stage.canonical_item_id,
                    session_stage.track_id,
                    session_stage.first_played_at,
                    session_stage.last_played_at,
                    session_stage.play_count,
                    NOW()
                FROM {LISTENBRAINZ_SESSION_STAGE_TABLE} session_stage
                WHERE session_stage.run_id = %s
                  AND COALESCE(session_stage.partition_key, '') = %s
                RETURNING 1
            )
            SELECT COUNT(*) FROM inserted_session_rows
            ''',
            [import_run_id, run_id, partition_key],
        )
        inserted_rows = int(cursor.fetchone()[0] or 0)
        cursor.execute(
            f'''
        DELETE FROM {LISTENBRAINZ_SESSION_STAGE_TABLE}
        WHERE run_id = %s
          AND COALESCE(partition_key, '') = %s
        ''',
            [run_id, partition_key],
        )
        _mark_finalize_checkpoint(
            cursor,
            run_id=run_id,
            phase=LISTENBRAINZ_FINALIZE_PHASE_HOT_BUILD,
            partition_key=partition_key,
        )
    return inserted_rows


def _count_table_rows(cursor, table_name: str, *, where_clause: str = '') -> int:
    where_sql = f' WHERE {where_clause}' if where_clause else ''
    cursor.execute(f'SELECT COUNT(*) FROM {table_name}{where_sql}')
    return int(cursor.fetchone()[0] or 0)


def _upsert_canonical_items_from_load_table(cursor, run_id: str, *, partition_key: str | None = None) -> None:
    if connection.vendor == 'postgresql':
        where_sql = 'WHERE run_id = %s'
        params: list[str] = [run_id]
        if partition_key is not None:
            where_sql += ' AND partition_key = %s'
            params.append(partition_key)
        cursor.execute(
            f'''
            INSERT INTO {CANONICAL_ITEM_TABLE} (
                id,
                item_type,
                canonical_key,
                track_id,
                created_at,
                updated_at
            )
            SELECT DISTINCT
                canonical_item_id,
                canonical_item_type,
                canonical_item_key,
                track_id,
                NOW(),
                NOW()
            FROM {LISTENBRAINZ_EVENT_LOAD_TABLE}
            {where_sql}
              AND canonical_item_id IS NOT NULL
              AND canonical_item_type IS NOT NULL
              AND canonical_item_key IS NOT NULL
            ON CONFLICT (canonical_key) DO UPDATE
            SET
                track_id = COALESCE({CANONICAL_ITEM_TABLE}.track_id, EXCLUDED.track_id),
                updated_at = NOW()
            ''',
            params,
        )
        return

    where_sql = 'WHERE run_id = ?'
    params = [run_id]
    if partition_key is not None:
        where_sql += ' AND partition_key = ?'
        params.append(partition_key)
    cursor.execute(
        f'''
        INSERT OR IGNORE INTO {CANONICAL_ITEM_TABLE} (
            id,
            item_type,
            canonical_key,
            track_id,
            created_at,
            updated_at
        )
        SELECT DISTINCT
            canonical_item_id,
            canonical_item_type,
            canonical_item_key,
            track_id,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP
        FROM {LISTENBRAINZ_EVENT_LOAD_TABLE}
        {where_sql}
          AND canonical_item_id IS NOT NULL
          AND canonical_item_type IS NOT NULL
          AND canonical_item_key IS NOT NULL
        ''',
        params,
    )


def _relation_exists(cursor, relation_name: str) -> bool:
    cursor.execute('SELECT to_regclass(%s)', [relation_name])
    return cursor.fetchone()[0] is not None


def _constraint_exists(cursor, relation_name: str, constraint_name: str) -> bool:
    cursor.execute(
        '''
        SELECT EXISTS (
            SELECT 1
            FROM pg_constraint c
            JOIN pg_class r ON r.oid = c.conrelid
            JOIN pg_namespace n ON n.oid = r.relnamespace
            WHERE n.nspname = current_schema()
              AND r.relname = %s
              AND c.conname = %s
        )
        ''',
        [relation_name, constraint_name],
    )
    return bool(cursor.fetchone()[0])


def _clear_finalize_checkpoints(cursor, run_id: str) -> None:
    cursor.execute(
        f'DELETE FROM {LISTENBRAINZ_FINALIZE_CHECKPOINT_TABLE} WHERE run_id = %s',
        [run_id],
    )


def _finalize_checkpoint_partition_key(partition_key: str | None = None) -> str:
    return str(partition_key or '')


def _mark_finalize_checkpoint(cursor, *, run_id: str, phase: str, partition_key: str | None = None) -> None:
    checkpoint_key = _finalize_checkpoint_partition_key(partition_key)
    if connection.vendor == 'postgresql':
        cursor.execute(
            f'''
            INSERT INTO {LISTENBRAINZ_FINALIZE_CHECKPOINT_TABLE} (
                run_id,
                phase,
                partition_key,
                completed_at
            )
            VALUES (%s::uuid, %s, %s, NOW())
            ON CONFLICT (run_id, phase, partition_key) DO NOTHING
            ''',
            [run_id, phase, checkpoint_key],
        )
        return

    cursor.execute(
        f'''
        INSERT OR IGNORE INTO {LISTENBRAINZ_FINALIZE_CHECKPOINT_TABLE} (
            run_id,
            phase,
            partition_key,
            completed_at
        )
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ''',
        [run_id, phase, checkpoint_key],
    )


def _finalize_phase_completed(cursor, *, run_id: str, phase: str) -> bool:
    cursor.execute(
        f'''
        SELECT EXISTS(
            SELECT 1
            FROM {LISTENBRAINZ_FINALIZE_CHECKPOINT_TABLE}
            WHERE run_id = %s
              AND phase = %s
              AND partition_key = %s
        )
        ''',
        [run_id, phase, ''],
    )
    return bool(cursor.fetchone()[0])


def _load_finalize_checkpointed_partitions(cursor, *, run_id: str, phase: str) -> set[str]:
    cursor.execute(
        f'''
        SELECT partition_key
        FROM {LISTENBRAINZ_FINALIZE_CHECKPOINT_TABLE}
        WHERE run_id = %s
          AND phase = %s
          AND partition_key <> %s
        ''',
        [run_id, phase, ''],
    )
    return {str(row[0]) for row in cursor.fetchall()}


def _drop_listenbrainz_shadow_tables(cursor) -> None:
    for table_name in (
        LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE,
        LISTENBRAINZ_EVENT_LEDGER_BACKUP_TABLE,
        LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE,
        LISTENBRAINZ_SESSION_TRACK_BACKUP_TABLE,
        LISTENBRAINZ_SESSION_STAGE_TABLE,
    ):
        cursor.execute(f'DROP TABLE IF EXISTS {table_name} CASCADE')


def _create_empty_listenbrainz_event_ledger_build_table(cursor) -> None:
    cursor.execute(
        f'''
        CREATE TABLE {LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE}
        (LIKE {LISTENBRAINZ_EVENT_LEDGER_TABLE} INCLUDING DEFAULTS)
        TABLESPACE {settings.MLCORE_PG_COLD_TABLESPACE_NAME}
        '''
    )


def _create_empty_listenbrainz_session_track_build_table(cursor) -> None:
    cursor.execute(
        f'''
        CREATE TABLE {LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE}
        (LIKE {LISTENBRAINZ_SESSION_TRACK_TABLE} INCLUDING DEFAULTS)
        TABLESPACE {settings.MLCORE_PG_HOT_TABLESPACE_NAME}
        '''
    )


def _ensure_listenbrainz_session_stage_table(cursor) -> None:
    if _relation_exists(cursor, LISTENBRAINZ_SESSION_STAGE_TABLE):
        return
    session_hot_ts = settings.MLCORE_PG_HOT_TABLESPACE_NAME
    cursor.execute(
        f'''
        CREATE UNLOGGED TABLE {LISTENBRAINZ_SESSION_STAGE_TABLE} (
            run_id uuid NOT NULL,
            partition_key varchar(16) NOT NULL,
            session_key bytea NOT NULL,
            canonical_item_id uuid NOT NULL,
            track_id uuid NULL,
            first_played_at timestamptz NOT NULL,
            last_played_at timestamptz NOT NULL,
            play_count integer NOT NULL
        )
        TABLESPACE {session_hot_ts}
        '''
    )
    cursor.execute(
        f'''
        CREATE INDEX IF NOT EXISTS {LISTENBRAINZ_SESSION_STAGE_TABLE}_run_partition_idx
        ON {LISTENBRAINZ_SESSION_STAGE_TABLE} (run_id, partition_key)
        '''
    )


def _finalize_listenbrainz_partition_into_build_tables(
    *,
    run_id: str,
    partition_key: str,
    import_run_id: str,
) -> FullIngestionMergeResult:
    with transaction.atomic():
        with connection.cursor() as cursor:
            staged_rows = _count_partition_rows(cursor, LISTENBRAINZ_EVENT_LOAD_TABLE, run_id, partition_key)
            _upsert_canonical_items_from_load_table(cursor, run_id, partition_key=partition_key)
            cursor.execute(
            f'''
            WITH deduplicated_events AS (
                SELECT DISTINCT ON (event_signature)
                    event_signature,
                    played_at,
                    session_key,
                    canonical_item_id,
                    track_id,
                    resolution_state,
                    cold_ref
                FROM {LISTENBRAINZ_EVENT_LOAD_TABLE}
                WHERE run_id = %s
                  AND partition_key = %s
                ORDER BY event_signature, cold_ref
            ),
            inserted_events AS (
                INSERT INTO {LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE} (
                    id,
                    import_run_id,
                    event_signature,
                    played_at,
                    session_key,
                    canonical_item_id,
                    track_id,
                    resolution_state,
                    cold_ref,
                    created_at
                )
                SELECT
                    {deterministic_uuid_sql("encode(deduplicated_events.event_signature, 'hex')")},
                    %s::uuid,
                    deduplicated_events.event_signature,
                    deduplicated_events.played_at,
                    deduplicated_events.session_key,
                    deduplicated_events.canonical_item_id,
                    deduplicated_events.track_id,
                    deduplicated_events.resolution_state,
                    deduplicated_events.cold_ref,
                    NOW()
                FROM deduplicated_events
                RETURNING canonical_item_id
            )
            SELECT
                COUNT(*) AS rows_merged,
                COUNT(canonical_item_id) AS rows_resolved,
                COUNT(*) FILTER (WHERE canonical_item_id IS NULL) AS rows_unresolved
            FROM inserted_events
            ''',
                [run_id, partition_key, import_run_id],
            )
            rows_merged, rows_resolved, rows_unresolved = [int(value or 0) for value in cursor.fetchone()]
            cursor.execute(
            f'''
            WITH inserted_session_rows AS (
                INSERT INTO {LISTENBRAINZ_SESSION_STAGE_TABLE} (
                    run_id,
                    partition_key,
                    session_key,
                    canonical_item_id,
                    track_id,
                    first_played_at,
                    last_played_at,
                    play_count
                )
                SELECT
                    %s::uuid,
                    %s,
                    session_delta.session_key,
                    session_delta.canonical_item_id,
                    session_delta.track_id,
                    session_delta.first_played_at,
                    session_delta.last_played_at,
                    session_delta.play_count
                FROM {LISTENBRAINZ_SESSION_LOAD_TABLE} session_delta
                WHERE session_delta.run_id = %s
                  AND session_delta.partition_key = %s
                RETURNING 1
            )
            SELECT COUNT(*) FROM inserted_session_rows
            ''',
                [run_id, partition_key, run_id, partition_key],
            )
            session_rows_merged = int(cursor.fetchone()[0] or 0)
            cursor.execute(
                f'DELETE FROM {LISTENBRAINZ_SESSION_LOAD_TABLE} WHERE run_id = %s AND partition_key = %s',
                [run_id, partition_key],
            )
            cursor.execute(
                f'DELETE FROM {LISTENBRAINZ_EVENT_LOAD_TABLE} WHERE run_id = %s AND partition_key = %s',
                [run_id, partition_key],
            )
            _mark_finalize_checkpoint(
                cursor,
                run_id=run_id,
                phase=LISTENBRAINZ_FINALIZE_PHASE_PARTITION_DRAIN,
                partition_key=partition_key,
            )

    return FullIngestionMergeResult(
        rows_merged=rows_merged,
        rows_deduplicated=max(0, staged_rows - rows_merged),
        rows_resolved=rows_resolved,
        rows_unresolved=rows_unresolved,
        session_rows_merged=session_rows_merged,
    )


def _create_listenbrainz_shadow_constraints_and_indexes(cursor) -> None:
    event_cold_ts = settings.MLCORE_PG_COLD_TABLESPACE_NAME
    session_hot_ts = settings.MLCORE_PG_HOT_TABLESPACE_NAME

    cursor.execute(
        (
            f'CREATE UNIQUE INDEX IF NOT EXISTS mlcore_lbe_build_pkey_idx '
            f'ON {LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE} (id) TABLESPACE {event_cold_ts}'
        )
    )
    if not _constraint_exists(cursor, LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE, 'mlcore_lbe_build_pkey'):
        cursor.execute(
            (
                f'ALTER TABLE {LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE} '
                f'ADD CONSTRAINT mlcore_lbe_build_pkey '
                f'PRIMARY KEY USING INDEX mlcore_lbe_build_pkey_idx'
            )
        )
    cursor.execute(
        (
            f'CREATE UNIQUE INDEX IF NOT EXISTS mlcore_lbe_build_event_signature_idx '
            f'ON {LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE} (event_signature) '
            f'TABLESPACE {event_cold_ts}'
        )
    )
    if not _constraint_exists(cursor, LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE, 'mlcore_lbe_build_event_signature_key'):
        cursor.execute(
            (
                f'ALTER TABLE {LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE} '
                f'ADD CONSTRAINT mlcore_lbe_build_event_signature_key '
                f'UNIQUE USING INDEX mlcore_lbe_build_event_signature_idx'
            )
        )
    if not _constraint_exists(cursor, LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE, 'mlcore_lbe_build_resolution_state_check'):
        cursor.execute(
            (
                f'ALTER TABLE {LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE} '
                f'ADD CONSTRAINT mlcore_lbe_build_resolution_state_check '
                f'CHECK (resolution_state >= 0)'
            )
        )
    if not _constraint_exists(cursor, LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE, 'mlcore_lbe_build_import_run_fk'):
        cursor.execute(
            (
                f'ALTER TABLE {LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE} '
                f'ADD CONSTRAINT mlcore_lbe_build_import_run_fk '
                f'FOREIGN KEY (import_run_id) REFERENCES mlcore_source_ingestion_run(id) '
                f'DEFERRABLE INITIALLY DEFERRED'
            )
        )
    if not _constraint_exists(cursor, LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE, 'mlcore_lbe_build_canonical_item_fk'):
        cursor.execute(
            (
                f'ALTER TABLE {LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE} '
                f'ADD CONSTRAINT mlcore_lbe_build_canonical_item_fk '
                f'FOREIGN KEY (canonical_item_id) REFERENCES {CANONICAL_ITEM_TABLE}(id) '
                f'DEFERRABLE INITIALLY DEFERRED'
            )
        )
    if not _constraint_exists(cursor, LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE, 'mlcore_lbe_build_track_fk'):
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
        ('mlcore_lbe_build_canonical_item_idx', 'canonical_item_id'),
        ('mlcore_lbe_build_track_idx', 'track_id'),
        ('mlcore_lbe_build_resolution_idx', 'resolution_state'),
        ('mlcore_lbe_build_import_run_fk_idx', 'import_run_id'),
        ('mlcore_lbe_build_played_at_idx', 'played_at'),
        ('mlcore_lbe_build_session_key_idx', 'session_key'),
        ('mlcore_lbe_build_canonical_item_fk_idx', 'canonical_item_id'),
        ('mlcore_lbe_build_track_fk_idx', 'track_id'),
    ):
        cursor.execute(
            f'CREATE INDEX IF NOT EXISTS {index_name} ON {LISTENBRAINZ_EVENT_LEDGER_BUILD_TABLE} ({column_list}) TABLESPACE {event_cold_ts}'
        )

    cursor.execute(
        (
            f'CREATE UNIQUE INDEX IF NOT EXISTS mlcore_lst_build_pkey_idx '
            f'ON {LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE} (id) TABLESPACE {session_hot_ts}'
        )
    )
    if not _constraint_exists(cursor, LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE, 'mlcore_lst_build_pkey'):
        cursor.execute(
            (
                f'ALTER TABLE {LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE} '
                f'ADD CONSTRAINT mlcore_lst_build_pkey '
                f'PRIMARY KEY USING INDEX mlcore_lst_build_pkey_idx'
            )
        )
    cursor.execute(
        (
            f'CREATE UNIQUE INDEX IF NOT EXISTS mlcore_lst_build_session_track_idx '
            f'ON {LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE} (session_key, canonical_item_id) '
            f'TABLESPACE {session_hot_ts}'
        )
    )
    if not _constraint_exists(cursor, LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE, 'mlcore_lst_build_session_track_key'):
        cursor.execute(
            (
                f'ALTER TABLE {LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE} '
                f'ADD CONSTRAINT mlcore_lst_build_session_track_key '
                f'UNIQUE USING INDEX mlcore_lst_build_session_track_idx'
            )
        )
    if not _constraint_exists(cursor, LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE, 'mlcore_lst_build_import_run_fk'):
        cursor.execute(
            (
                f'ALTER TABLE {LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE} '
                f'ADD CONSTRAINT mlcore_lst_build_import_run_fk '
                f'FOREIGN KEY (import_run_id) REFERENCES mlcore_source_ingestion_run(id) '
                f'DEFERRABLE INITIALLY DEFERRED'
            )
        )
    if not _constraint_exists(cursor, LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE, 'mlcore_lst_build_canonical_item_fk'):
        cursor.execute(
            (
                f'ALTER TABLE {LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE} '
                f'ADD CONSTRAINT mlcore_lst_build_canonical_item_fk '
                f'FOREIGN KEY (canonical_item_id) REFERENCES {CANONICAL_ITEM_TABLE}(id) '
                f'DEFERRABLE INITIALLY DEFERRED'
            )
        )
    if not _constraint_exists(cursor, LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE, 'mlcore_lst_build_track_fk'):
        cursor.execute(
            (
                f'ALTER TABLE {LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE} '
                f'ADD CONSTRAINT mlcore_lst_build_track_fk '
                f'FOREIGN KEY (track_id) REFERENCES catalog_track(juke_id) '
                f'DEFERRABLE INITIALLY DEFERRED'
            )
        )
    for index_name, column_list in (
        ('mlcore_lst_build_canonical_item_idx', 'canonical_item_id'),
        ('mlcore_lst_build_track_idx', 'track_id'),
        ('mlcore_lst_build_import_idx', 'import_run_id'),
        ('mlcore_lst_build_last_played_idx', 'last_played_at'),
        ('mlcore_lst_build_import_run_fk_idx', 'import_run_id'),
        ('mlcore_lst_build_session_key_idx', 'session_key'),
        ('mlcore_lst_build_canonical_item_fk_idx', 'canonical_item_id'),
        ('mlcore_lst_build_track_fk_idx', 'track_id'),
    ):
        cursor.execute(
            (
                f'CREATE INDEX IF NOT EXISTS {index_name} '
                f'ON {LISTENBRAINZ_SESSION_TRACK_BUILD_TABLE} ({column_list}) '
                f'TABLESPACE {session_hot_ts}'
            )
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
            ('mlcore_lbe_build_canonical_item_fk', 'mlcore_lbe_canonical_item_fk'),
            ('mlcore_lbe_build_track_fk', 'mlcore_listenbrainz__track_id_3f187a0b_fk_catalog_t'),
        ):
            cursor.execute(
                f'ALTER TABLE {LISTENBRAINZ_EVENT_LEDGER_TABLE} RENAME CONSTRAINT {old_name} TO {new_name}'
            )

        for old_name, new_name in (
            ('mlcore_lbe_build_import_idx', 'mlcore_lbe_import__e9179a_idx'),
            ('mlcore_lbe_build_canonical_item_idx', 'mlcore_lbe_canonic_9067f9_idx'),
            ('mlcore_lbe_build_track_idx', 'mlcore_lbe_track_i_4c8647_idx'),
            ('mlcore_lbe_build_resolution_idx', 'mlcore_lbe_resolut_8e2ae0_idx'),
            ('mlcore_lbe_build_import_run_fk_idx', 'mlcore_listenbrainz_event_ledger_import_run_id_caebef5c'),
            ('mlcore_lbe_build_played_at_idx', 'mlcore_listenbrainz_event_ledger_played_at_dac9bed0'),
            ('mlcore_lbe_build_session_key_idx', 'mlcore_listenbrainz_event_ledger_session_key_1515c241'),
            ('mlcore_lbe_build_canonical_item_fk_idx', 'mlcore_lbe_canonical_item_fk_idx'),
            ('mlcore_lbe_build_track_fk_idx', 'mlcore_listenbrainz_event_ledger_track_id_3f187a0b'),
        ):
            cursor.execute(f'ALTER INDEX {old_name} RENAME TO {new_name}')

        for old_name, new_name in (
            ('mlcore_lst_build_pkey', 'mlcore_listenbrainz_session_track_pkey'),
            ('mlcore_lst_build_session_track_key', 'mlcore_lst_session_key_canonical_item_id_uniq'),
            ('mlcore_lst_build_import_run_fk', 'mlcore_listenbrainz__import_run_id_a2d035d9_fk_mlcore_so'),
            ('mlcore_lst_build_canonical_item_fk', 'mlcore_lst_canonical_item_fk'),
            ('mlcore_lst_build_track_fk', 'mlcore_listenbrainz__track_id_7ed8fb5a_fk_catalog_t'),
        ):
            cursor.execute(
                f'ALTER TABLE {LISTENBRAINZ_SESSION_TRACK_TABLE} RENAME CONSTRAINT {old_name} TO {new_name}'
            )

        for old_name, new_name in (
            ('mlcore_lst_build_canonical_item_idx', 'mlcore_lst_canonic_78087f_idx'),
            ('mlcore_lst_build_track_idx', 'mlcore_lst_track_i_5d5e20_idx'),
            ('mlcore_lst_build_import_idx', 'mlcore_lst_import__6d7bf6_idx'),
            ('mlcore_lst_build_last_played_idx', 'mlcore_lst_last_pl_4a4ec9_idx'),
            ('mlcore_lst_build_import_run_fk_idx', 'mlcore_listenbrainz_session_track_import_run_id_a2d035d9'),
            ('mlcore_lst_build_session_key_idx', 'mlcore_listenbrainz_session_track_session_key_33f13768'),
            ('mlcore_lst_build_canonical_item_fk_idx', 'mlcore_lst_canonical_item_fk_idx'),
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
