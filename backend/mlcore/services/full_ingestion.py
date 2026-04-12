from __future__ import annotations

import csv
import hashlib
import json
import shutil
import tarfile
import uuid
from collections import defaultdict
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from threading import Lock
from pathlib import Path
from typing import Any, Iterator, Protocol

from django.conf import settings
from django.db import close_old_connections, connection
from django.utils import timezone

from mlcore.ingestion.listenbrainz import (
    configured_dump_path,
    infer_source_version_from_path,
    iter_listenbrainz_json_payloads,
    parse_listenbrainz_payload,
)
from mlcore.models import SourceIngestionRun
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
    'rows_merged',
    'rows_deduplicated',
    'rows_resolved',
    'rows_unresolved',
    'rows_malformed',
    'partitions_completed',
    'partitions_loaded',
    'partitions_merged',
    'partitions_failed',
)
LISTENBRAINZ_EVENT_STAGE_TABLE = 'mlcore_listenbrainz_event_stage'


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
    rows_parsed: int
    rows_staged: int
    rows_resolved: int
    rows_unresolved: int
    rows_malformed: int
    stage_file_path: str


@dataclass(frozen=True)
class FullIngestionMergeResult:
    partition_key: str
    rows_merged: int
    rows_deduplicated: int
    rows_resolved: int
    rows_unresolved: int
    session_rows_merged: int


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

    def iter_partition_artifacts(self, plan: FullIngestionPlan) -> Iterator[FullIngestionPartitionArtifact]:
        ...

    def ensure_staging_tables(self) -> None:
        ...

    def load_partition_to_staging(
        self,
        plan: FullIngestionPlan,
        partition: FullIngestionPartitionPlan,
    ) -> FullIngestionCopyResult:
        ...

    def merge_partition_to_final(
        self,
        plan: FullIngestionPlan,
        partition: FullIngestionPartitionPlan,
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

    def iter_partition_artifacts(self, plan: FullIngestionPlan) -> Iterator[FullIngestionPartitionArtifact]:
        archive_path = Path(plan.archive_path)
        partition_root = Path(plan.partition_root)
        with tarfile.open(archive_path, 'r:*') as archive:
            for member in archive:
                relative_path = listenbrainz_shard_relative_path(member.name)
                if relative_path is None:
                    continue

                extracted = archive.extractfile(member)
                if extracted is None:
                    continue

                partition_index = partition_index_for_path(
                    relative_path.as_posix(),
                    partition_count=plan.partition_count,
                )
                partition_key = f'p{partition_index:03d}'
                destination = partition_root / partition_key / 'input' / relative_path
                destination.parent.mkdir(parents=True, exist_ok=True)
                temp_destination = destination.with_name(destination.name + '.part')
                if temp_destination.exists():
                    temp_destination.unlink()

                digest = hashlib.sha256()
                size_bytes = 0
                with temp_destination.open('wb') as handle:
                    while True:
                        chunk = extracted.read(1024 * 1024)
                        if not chunk:
                            break
                        handle.write(chunk)
                        digest.update(chunk)
                        size_bytes += len(chunk)
                temp_destination.replace(destination)
                yield FullIngestionPartitionArtifact(
                    partition_key=partition_key,
                    partition_index=partition_index,
                    source_member_name=member.name,
                    relative_path=relative_path.as_posix(),
                    size_bytes=size_bytes,
                    sha256=digest.hexdigest(),
                )

    def ensure_staging_tables(self) -> None:
        ensure_listenbrainz_staging_tables()

    def load_partition_to_staging(
        self,
        plan: FullIngestionPlan,
        partition: FullIngestionPartitionPlan,
    ) -> FullIngestionCopyResult:
        return load_listenbrainz_partition_to_staging(plan, partition)

    def merge_partition_to_final(
        self,
        plan: FullIngestionPlan,
        partition: FullIngestionPartitionPlan,
        *,
        source_ingestion_run: SourceIngestionRun,
    ) -> FullIngestionMergeResult:
        return merge_listenbrainz_partition_to_final(
            plan,
            partition,
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


def configured_full_ingestion_metrics_path() -> Path | None:
    value = str(getattr(settings, 'MLCORE_FULL_INGESTION_TEXTFILE_METRICS_PATH', '') or '').strip()
    if not value:
        return None
    return Path(value)


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
            'partitions_completed': 0,
            'partitions_failed': 0,
        },
    )
    write_full_ingestion_plan(running_plan)
    write_full_ingestion_metrics(running_plan)

    provider = get_full_ingestion_provider(running_plan.provider)
    artifacts_by_partition: dict[int, list[FullIngestionPartitionArtifact]] = defaultdict(list)
    counters = dict(running_plan.counters)

    try:
        for artifact in provider.iter_partition_artifacts(running_plan):
            artifacts_by_partition[artifact.partition_index].append(artifact)
            counters['artifacts_discovered'] = int(counters.get('artifacts_discovered') or 0) + 1
            counters['artifacts_partitioned'] = int(counters.get('artifacts_partitioned') or 0) + 1
            counters['input_bytes_partitioned'] = int(counters.get('input_bytes_partitioned') or 0) + artifact.size_bytes
            running_plan = replace(
                running_plan,
                counters=counters,
                updated_at=datetime.now(tz=UTC).isoformat(),
            )
            write_full_ingestion_plan(running_plan)
            write_full_ingestion_metrics(running_plan)
    except Exception:
        failed_plan = replace(
            running_plan,
            status=FULL_INGESTION_STATUS_FAILED,
            updated_at=datetime.now(tz=UTC).isoformat(),
            counters={
                **counters,
                'partitions_failed': running_plan.partition_count,
            },
        )
        write_full_ingestion_plan(failed_plan)
        write_full_ingestion_metrics(failed_plan)
        raise

    finalized_partitions: list[FullIngestionPartitionPlan] = []
    for partition in running_plan.partitions:
        artifacts = sorted(
            artifacts_by_partition.get(partition.index, []),
            key=lambda artifact: artifact.relative_path,
        )
        write_full_ingestion_partition_manifest(
            running_plan,
            partition=partition,
            artifacts=artifacts,
        )
        finalized_partitions.append(
            replace(
                partition,
                state='partitioned',
                actual_input_bytes=sum(artifact.size_bytes for artifact in artifacts),
                actual_artifact_count=len(artifacts),
            )
        )

    completed_counters = {
        **counters,
        'partitions_completed': len(finalized_partitions),
        'partitions_failed': 0,
    }
    completed_plan = replace(
        running_plan,
        updated_at=datetime.now(tz=UTC).isoformat(),
        counters=completed_counters,
        partitions=finalized_partitions,
    )
    write_full_ingestion_plan(completed_plan)
    write_full_ingestion_metrics(completed_plan)
    return completed_plan


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
    artifacts: list[FullIngestionPartitionArtifact],
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
        'artifact_count': len(artifacts),
        'total_input_bytes': sum(artifact.size_bytes for artifact in artifacts),
        'artifacts': [
            {
                'source_member_name': artifact.source_member_name,
                'relative_path': artifact.relative_path,
                'size_bytes': artifact.size_bytes,
                'sha256': artifact.sha256,
            }
            for artifact in artifacts
        ],
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
        raise ValueError('Copy stage requires all partitions to be materialized first.')

    if all(partition.state == 'loaded' for partition in plan.partitions) and not force:
        return plan

    provider = get_full_ingestion_provider(plan.provider)
    provider.ensure_staging_tables()

    running_plan = replace(
        plan,
        stage=FULL_INGESTION_STAGE_COPY,
        status=FULL_INGESTION_STATUS_RUNNING,
        updated_at=datetime.now(tz=UTC).isoformat(),
        counters={
            **plan.counters,
            'rows_parsed': 0 if force else int(plan.counters.get('rows_parsed') or 0),
            'rows_staged': 0 if force else int(plan.counters.get('rows_staged') or 0),
            'rows_resolved': 0 if force else int(plan.counters.get('rows_resolved') or 0),
            'rows_unresolved': 0 if force else int(plan.counters.get('rows_unresolved') or 0),
            'rows_malformed': 0 if force else int(plan.counters.get('rows_malformed') or 0),
            'partitions_loaded': 0 if force else int(plan.counters.get('partitions_loaded') or 0),
        },
    )
    write_full_ingestion_plan(running_plan)
    write_full_ingestion_metrics(running_plan)

    counters = dict(running_plan.counters)
    finalized_partitions: list[FullIngestionPartitionPlan] = list(running_plan.partitions)
    loaded_count = 0 if force else sum(1 for partition in finalized_partitions if partition.state == 'loaded')
    counters['partitions_loaded'] = loaded_count

    try:
        for index, partition in enumerate(finalized_partitions):
            if partition.state == 'loaded' and not force:
                continue

            result = provider.load_partition_to_staging(running_plan, partition)
            counters['rows_parsed'] = int(counters.get('rows_parsed') or 0) + result.rows_parsed
            counters['rows_staged'] = int(counters.get('rows_staged') or 0) + result.rows_staged
            counters['rows_resolved'] = int(counters.get('rows_resolved') or 0) + result.rows_resolved
            counters['rows_unresolved'] = int(counters.get('rows_unresolved') or 0) + result.rows_unresolved
            counters['rows_malformed'] = int(counters.get('rows_malformed') or 0) + result.rows_malformed
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
            write_full_ingestion_plan(running_plan)
            write_full_ingestion_metrics(running_plan)
    except Exception:
        if 'index' in locals():
            failed_partition = finalized_partitions[index]
            finalized_partitions[index] = replace(failed_partition, state='failed')
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
        write_full_ingestion_plan(failed_plan)
        write_full_ingestion_metrics(failed_plan)
        raise

    completed_plan = replace(
        running_plan,
        updated_at=datetime.now(tz=UTC).isoformat(),
        counters=dict(counters),
        partitions=list(finalized_partitions),
    )
    write_full_ingestion_plan(completed_plan)
    write_full_ingestion_metrics(completed_plan)
    return completed_plan


def execute_full_ingestion_merge_stage(
    plan: FullIngestionPlan,
    *,
    force: bool = False,
) -> FullIngestionPlan:
    if any(partition.state not in ('loaded', 'merged') for partition in plan.partitions):
        raise ValueError('Merge stage requires all partitions to be loaded into staging first.')

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
            'rows_resolved': 0 if force else int(plan.counters.get('rows_resolved') or 0),
            'rows_unresolved': 0 if force else int(plan.counters.get('rows_unresolved') or 0),
            'partitions_merged': 0 if force else int(plan.counters.get('partitions_merged') or 0),
        },
    )
    write_full_ingestion_plan(running_plan)
    write_full_ingestion_metrics(running_plan)

    counters = dict(running_plan.counters)
    finalized_partitions: list[FullIngestionPartitionPlan] = list(running_plan.partitions)
    merged_count = 0 if force else sum(1 for partition in finalized_partitions if partition.state == 'merged')
    counters['partitions_merged'] = merged_count

    try:
        for index, partition in enumerate(finalized_partitions):
            if partition.state == 'merged' and not force:
                continue

            result = provider.merge_partition_to_final(
                running_plan,
                partition,
                source_ingestion_run=source_ingestion_run,
            )
            counters['rows_merged'] = int(counters.get('rows_merged') or 0) + result.rows_merged
            counters['rows_deduplicated'] = (
                int(counters.get('rows_deduplicated') or 0) + result.rows_deduplicated
            )
            counters['rows_resolved'] = int(counters.get('rows_resolved') or 0) + result.rows_resolved
            counters['rows_unresolved'] = int(counters.get('rows_unresolved') or 0) + result.rows_unresolved
            counters['partitions_merged'] = int(counters.get('partitions_merged') or 0) + 1
            finalized_partitions[index] = replace(partition, state='merged')
            write_full_ingestion_merge_manifest(
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
            write_full_ingestion_plan(running_plan)
            write_full_ingestion_metrics(running_plan)
    except Exception as exc:
        if 'index' in locals():
            failed_partition = finalized_partitions[index]
            finalized_partitions[index] = replace(failed_partition, state='failed')
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
        write_full_ingestion_plan(failed_plan)
        write_full_ingestion_metrics(failed_plan)
        _mark_full_ingestion_source_run_failed(source_ingestion_run, failed_plan, error=str(exc))
        raise

    completed_plan = replace(
        running_plan,
        stage=FULL_INGESTION_STAGE_COMPLETE,
        status=FULL_INGESTION_STATUS_SUCCEEDED,
        updated_at=datetime.now(tz=UTC).isoformat(),
        counters=dict(counters),
        partitions=list(finalized_partitions),
    )
    write_full_ingestion_plan(completed_plan)
    write_full_ingestion_metrics(completed_plan)
    finalize_full_ingestion_source_run(source_ingestion_run, completed_plan)
    return completed_plan


def execute_full_ingestion_pipeline(
    plan: FullIngestionPlan,
    *,
    force: bool = False,
) -> FullIngestionPlan:
    if plan.stage == FULL_INGESTION_STAGE_PLANNED:
        plan = execute_full_ingestion_partition_stage(plan, force=force)
    elif any(partition.state == 'pending' for partition in plan.partitions):
        raise ValueError('Pipeline execution requires all partitions to be materialized first.')

    provider = get_full_ingestion_provider(plan.provider)
    provider.ensure_staging_tables()
    source_ingestion_run, source_ingestion_run_id = ensure_full_ingestion_source_run(plan)
    lane_count = max(1, min(plan.load_workers, plan.merge_workers))

    normalized_partitions = _normalize_partitions_for_pipeline(plan.partitions, force=force)
    running_plan = replace(
        plan,
        stage=FULL_INGESTION_STAGE_PIPELINE,
        status=FULL_INGESTION_STATUS_RUNNING,
        source_ingestion_run_id=str(source_ingestion_run_id),
        updated_at=datetime.now(tz=UTC).isoformat(),
        counters=_pipeline_counters_for_start(plan.counters, force=force),
        partitions=normalized_partitions,
    )
    _persist_full_ingestion_state(running_plan)

    coordinator = _FullIngestionPipelineCoordinator(
        plan=running_plan,
        provider=provider,
        source_ingestion_run=source_ingestion_run,
    )
    try:
        completed_plan = coordinator.run(lane_count=lane_count)
    except Exception as exc:
        failed_plan = replace(
            coordinator.plan,
            status=FULL_INGESTION_STATUS_FAILED,
            updated_at=datetime.now(tz=UTC).isoformat(),
            counters={
                **coordinator.plan.counters,
                'partitions_failed': _pipeline_failed_partition_count(coordinator.plan.partitions),
            },
        )
        _persist_full_ingestion_state(failed_plan)
        _mark_full_ingestion_source_run_failed(source_ingestion_run, failed_plan, error=str(exc))
        raise

    final_plan = replace(
        completed_plan,
        stage=FULL_INGESTION_STAGE_COMPLETE,
        status=FULL_INGESTION_STATUS_SUCCEEDED,
        updated_at=datetime.now(tz=UTC).isoformat(),
    )
    _persist_full_ingestion_state(final_plan)
    finalize_full_ingestion_source_run(source_ingestion_run, final_plan)
    return final_plan


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
        'rows_parsed': result.rows_parsed,
        'rows_staged': result.rows_staged,
        'rows_resolved': result.rows_resolved,
        'rows_unresolved': result.rows_unresolved,
        'rows_malformed': result.rows_malformed,
        'stage_file_path': result.stage_file_path,
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


@dataclass
class _PipelinePartitionOutcome:
    partition_key: str
    copy_result: FullIngestionCopyResult
    merge_result: FullIngestionMergeResult
    copy_completed: bool


class _FullIngestionPipelineCoordinator:
    def __init__(
        self,
        *,
        plan: FullIngestionPlan,
        provider: FullDatasetIngestionProvider,
        source_ingestion_run: SourceIngestionRun,
    ) -> None:
        self.plan = plan
        self.provider = provider
        self.source_ingestion_run = source_ingestion_run
        self._lock = Lock()

    def run(self, *, lane_count: int) -> FullIngestionPlan:
        partition_keys = [
            partition.partition_key
            for partition in self.plan.partitions
            if partition.state != 'merged'
        ]
        if not partition_keys:
            return self.plan

        partition_iter = iter(partition_keys)
        future_to_partition: dict[Any, str] = {}
        with ThreadPoolExecutor(max_workers=lane_count) as executor:
            for _ in range(min(lane_count, len(partition_keys))):
                partition_key = next(partition_iter, None)
                if partition_key is None:
                    break
                future = executor.submit(self._run_partition_lane, partition_key)
                future_to_partition[future] = partition_key

            while future_to_partition:
                done, _ = wait(future_to_partition.keys(), return_when=FIRST_COMPLETED)
                for future in done:
                    partition_key = future_to_partition.pop(future)
                    outcome = future.result()
                    self._record_partition_success(outcome)
                    next_partition_key = next(partition_iter, None)
                    if next_partition_key is not None:
                        next_future = executor.submit(self._run_partition_lane, next_partition_key)
                        future_to_partition[next_future] = next_partition_key

        return self.plan

    def _run_partition_lane(self, partition_key: str) -> _PipelinePartitionOutcome:
        close_old_connections()
        try:
            self.provider.ensure_staging_tables()
            partition = self._partition_by_key(partition_key)
            if partition.state == 'loaded':
                copy_result = FullIngestionCopyResult(
                    partition_key=partition_key,
                    rows_parsed=0,
                    rows_staged=0,
                    rows_resolved=0,
                    rows_unresolved=0,
                    rows_malformed=0,
                    stage_file_path='',
                )
                copy_completed = False
            else:
                self._mark_partition_state(partition_key, 'loading')
                partition = self._partition_by_key(partition_key)
                copy_result = self.provider.load_partition_to_staging(self.plan, partition)
                copy_completed = True
            self._mark_partition_state(partition_key, 'merging')
            partition = self._partition_by_key(partition_key)
            merge_result = self.provider.merge_partition_to_final(
                self.plan,
                partition,
                source_ingestion_run=self.source_ingestion_run,
            )
            return _PipelinePartitionOutcome(
                partition_key=partition_key,
                copy_result=copy_result,
                merge_result=merge_result,
                copy_completed=copy_completed,
            )
        except Exception:
            self._mark_partition_state(partition_key, 'failed')
            raise
        finally:
            close_old_connections()

    def _record_partition_success(self, outcome: _PipelinePartitionOutcome) -> None:
        with self._lock:
            partition = self._partition_by_key(outcome.partition_key)
            if outcome.copy_result.stage_file_path:
                write_full_ingestion_copy_manifest(
                    self.plan,
                    partition=partition,
                    result=outcome.copy_result,
                )
            write_full_ingestion_merge_manifest(
                self.plan,
                partition=partition,
                result=outcome.merge_result,
            )
            counters = {
                **self.plan.counters,
                'rows_parsed': int(self.plan.counters.get('rows_parsed') or 0) + outcome.copy_result.rows_parsed,
                'rows_staged': int(self.plan.counters.get('rows_staged') or 0) + outcome.copy_result.rows_staged,
                'rows_merged': int(self.plan.counters.get('rows_merged') or 0) + outcome.merge_result.rows_merged,
                'rows_deduplicated': (
                    int(self.plan.counters.get('rows_deduplicated') or 0) + outcome.merge_result.rows_deduplicated
                ),
                'rows_resolved': int(self.plan.counters.get('rows_resolved') or 0) + outcome.merge_result.rows_resolved,
                'rows_unresolved': (
                    int(self.plan.counters.get('rows_unresolved') or 0) + outcome.merge_result.rows_unresolved
                ),
                'rows_malformed': (
                    int(self.plan.counters.get('rows_malformed') or 0) + outcome.copy_result.rows_malformed
                ),
                'partitions_loaded': (
                    int(self.plan.counters.get('partitions_loaded') or 0)
                    + (1 if outcome.copy_completed else 0)
                ),
                'partitions_merged': int(self.plan.counters.get('partitions_merged') or 0) + 1,
                'partitions_failed': _pipeline_failed_partition_count(self.plan.partitions),
            }
            self.plan = replace(
                self.plan,
                updated_at=datetime.now(tz=UTC).isoformat(),
                counters=counters,
                partitions=_replace_partition_state(self.plan.partitions, outcome.partition_key, 'merged'),
            )
            _persist_full_ingestion_state(self.plan)

    def _mark_partition_state(self, partition_key: str, state: str) -> None:
        with self._lock:
            self.plan = replace(
                self.plan,
                updated_at=datetime.now(tz=UTC).isoformat(),
                partitions=_replace_partition_state(self.plan.partitions, partition_key, state),
                counters={
                    **self.plan.counters,
                    'partitions_failed': _pipeline_failed_partition_count(
                        _replace_partition_state(self.plan.partitions, partition_key, state)
                    ),
                },
            )
            _persist_full_ingestion_state(self.plan)

    def _partition_by_key(self, partition_key: str) -> FullIngestionPartitionPlan:
        for partition in self.plan.partitions:
            if partition.partition_key == partition_key:
                return partition
        raise ValueError(f'Unknown full-ingestion partition {partition_key}')


def _pipeline_counters_for_start(counters: dict[str, int], *, force: bool) -> dict[str, int]:
    if not force:
        return {
            **counters,
            'rows_parsed': int(counters.get('rows_parsed') or 0),
            'rows_staged': int(counters.get('rows_staged') or 0),
            'rows_merged': int(counters.get('rows_merged') or 0),
            'rows_deduplicated': int(counters.get('rows_deduplicated') or 0),
            'rows_resolved': int(counters.get('rows_resolved') or 0),
            'rows_unresolved': int(counters.get('rows_unresolved') or 0),
            'rows_malformed': int(counters.get('rows_malformed') or 0),
            'partitions_loaded': int(counters.get('partitions_loaded') or 0),
            'partitions_merged': int(counters.get('partitions_merged') or 0),
            'partitions_failed': int(counters.get('partitions_failed') or 0),
        }
    return {
        **counters,
        'rows_parsed': 0,
        'rows_staged': 0,
        'rows_merged': 0,
        'rows_deduplicated': 0,
        'rows_resolved': 0,
        'rows_unresolved': 0,
        'rows_malformed': 0,
        'partitions_loaded': 0,
        'partitions_merged': 0,
        'partitions_failed': 0,
    }


def _normalize_partitions_for_pipeline(
    partitions: list[FullIngestionPartitionPlan],
    *,
    force: bool,
) -> list[FullIngestionPartitionPlan]:
    normalized: list[FullIngestionPartitionPlan] = []
    for partition in partitions:
        if force and partition.state in ('loaded', 'merged', 'loading', 'merging'):
            normalized.append(replace(partition, state='partitioned'))
            continue
        if partition.state in ('loading', 'merging'):
            normalized.append(replace(partition, state='partitioned'))
            continue
        normalized.append(partition)
    return normalized


def _replace_partition_state(
    partitions: list[FullIngestionPartitionPlan],
    partition_key: str,
    state: str,
) -> list[FullIngestionPartitionPlan]:
    return [
        replace(partition, state=state) if partition.partition_key == partition_key else partition
        for partition in partitions
    ]


def _pipeline_failed_partition_count(partitions: list[FullIngestionPartitionPlan]) -> int:
    return sum(1 for partition in partitions if partition.state == 'failed')


def _persist_full_ingestion_state(plan: FullIngestionPlan) -> None:
    write_full_ingestion_plan(plan)
    write_full_ingestion_metrics(plan)


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
    elapsed_seconds = max(0.0, (updated_at - created_at).total_seconds())

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


def ensure_listenbrainz_staging_tables() -> None:
    with connection.cursor() as cursor:
        if connection.vendor == 'postgresql':
            cursor.execute(
                f'''
                CREATE UNLOGGED TABLE IF NOT EXISTS {LISTENBRAINZ_EVENT_STAGE_TABLE} (
                    run_id uuid NOT NULL,
                    partition_key varchar(16) NOT NULL,
                    origin varchar(1024) NOT NULL,
                    line_number integer NOT NULL,
                    entry_index integer NOT NULL,
                    source_user_id varchar(64) NOT NULL,
                    played_at timestamptz NOT NULL,
                    session_key bytea NOT NULL,
                    event_signature bytea NOT NULL,
                    track_identifier_candidates jsonb NOT NULL,
                    payload jsonb NOT NULL,
                    metadata jsonb NOT NULL,
                    recording_mbid uuid NULL,
                    release_mbid uuid NULL,
                    recording_msid text NOT NULL,
                    release_msid text NOT NULL,
                    track_name text NOT NULL,
                    artist_name text NOT NULL,
                    release_name text NOT NULL
                )
                '''
            )
            cursor.execute(
                f'''
                CREATE INDEX IF NOT EXISTS {LISTENBRAINZ_EVENT_STAGE_TABLE}_run_partition_idx
                ON {LISTENBRAINZ_EVENT_STAGE_TABLE} (run_id, partition_key)
                '''
            )
        else:
            cursor.execute(
                f'''
                CREATE TABLE IF NOT EXISTS {LISTENBRAINZ_EVENT_STAGE_TABLE} (
                    run_id text NOT NULL,
                    partition_key text NOT NULL,
                    origin text NOT NULL,
                    line_number integer NOT NULL,
                    entry_index integer NOT NULL,
                    source_user_id text NOT NULL,
                    played_at text NOT NULL,
                    session_key blob NOT NULL,
                    event_signature blob NOT NULL,
                    track_identifier_candidates text NOT NULL,
                    payload text NOT NULL,
                    metadata text NOT NULL,
                    recording_mbid text NULL,
                    release_mbid text NULL,
                    recording_msid text NOT NULL,
                    release_msid text NOT NULL,
                    track_name text NOT NULL,
                    artist_name text NOT NULL,
                    release_name text NOT NULL
                )
                '''
            )
            cursor.execute(
                f'''
                CREATE INDEX IF NOT EXISTS {LISTENBRAINZ_EVENT_STAGE_TABLE}_run_partition_idx
                ON {LISTENBRAINZ_EVENT_STAGE_TABLE} (run_id, partition_key)
                '''
            )


def load_listenbrainz_partition_to_staging(
    plan: FullIngestionPlan,
    partition: FullIngestionPartitionPlan,
) -> FullIngestionCopyResult:
    partition_root = Path(plan.partition_root) / partition.partition_key
    input_root = partition_root / 'input'
    stage_root = partition_root / 'staging'
    stage_root.mkdir(parents=True, exist_ok=True)
    stage_file_path = stage_root / 'listenbrainz_event_stage.csv'

    rows_parsed = 0
    rows_staged = 0
    rows_resolved = 0
    rows_unresolved = 0
    rows_malformed = 0

    with stage_file_path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        for artifact_path in sorted(input_root.rglob('*.listens')):
            origin = artifact_path.relative_to(input_root).as_posix()
            with artifact_path.open('r', encoding='utf-8') as artifact_handle:
                for payload, error, _, line_number, entry_index in iter_listenbrainz_json_payloads(
                    artifact_handle,
                    origin=origin,
                ):
                    if error:
                        rows_malformed += 1
                        continue

                    assert payload is not None
                    try:
                        parsed = parse_listenbrainz_payload(payload)
                    except ValueError:
                        rows_malformed += 1
                        continue

                    rows_parsed += 1
                    recording_mbid = str(parsed.recording_mbid) if parsed.recording_mbid else r'\N'
                    release_mbid = str(parsed.release_mbid) if parsed.release_mbid else r'\N'
                    writer.writerow(
                        [
                            plan.run_id,
                            partition.partition_key,
                            origin,
                            line_number,
                            entry_index,
                            parsed.source_user_id,
                            parsed.played_at.isoformat(),
                            _bytea_hex(parsed.session_key),
                            _bytea_hex(parsed.source_event_signature),
                            json.dumps(parsed.track_identifier_candidates, sort_keys=True),
                            json.dumps(parsed.payload, sort_keys=True),
                            json.dumps(parsed.metadata, sort_keys=True),
                            recording_mbid,
                            release_mbid,
                            parsed.recording_msid,
                            parsed.release_msid,
                            parsed.track_name,
                            parsed.artist_name,
                            parsed.release_name,
                        ]
                    )
                    rows_staged += 1

    with connection.cursor() as cursor:
        cursor.execute(
            f'DELETE FROM {LISTENBRAINZ_EVENT_STAGE_TABLE} WHERE run_id = %s AND partition_key = %s',
            [plan.run_id, partition.partition_key],
        )

    _copy_csv_into_listenbrainz_stage(stage_file_path)
    return FullIngestionCopyResult(
        partition_key=partition.partition_key,
        rows_parsed=rows_parsed,
        rows_staged=rows_staged,
        rows_resolved=rows_resolved,
        rows_unresolved=rows_unresolved,
        rows_malformed=rows_malformed,
        stage_file_path=str(stage_file_path),
    )


def _copy_csv_into_listenbrainz_stage(stage_file_path: Path) -> None:
    copy_sql = (
        f'COPY {LISTENBRAINZ_EVENT_STAGE_TABLE} ('
        'run_id, partition_key, origin, line_number, entry_index, source_user_id, '
        'played_at, session_key, event_signature, track_identifier_candidates, payload, metadata, '
        'recording_mbid, release_mbid, recording_msid, release_msid, track_name, artist_name, release_name'
        ") FROM STDIN WITH (FORMAT csv, NULL '\\N')"
    )

    if connection.vendor != 'postgresql':
        with stage_file_path.open('r', encoding='utf-8', newline='') as handle, connection.cursor() as cursor:
            reader = csv.reader(handle)
            rows = list(reader)
            cursor.executemany(
                f'''
                INSERT INTO {LISTENBRAINZ_EVENT_STAGE_TABLE} (
                    run_id, partition_key, origin, line_number, entry_index, source_user_id,
                    played_at, session_key, event_signature, track_identifier_candidates, payload, metadata,
                    recording_mbid, release_mbid, recording_msid, release_msid, track_name, artist_name, release_name
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                rows,
            )
        return

    connection.ensure_connection()
    with stage_file_path.open('r', encoding='utf-8', newline='') as handle:
        with connection.cursor() as cursor:
            raw_cursor = getattr(cursor, 'cursor', cursor)
            if hasattr(raw_cursor, 'copy_expert'):
                raw_cursor.copy_expert(copy_sql, handle)
                return

    raw_connection = connection.connection
    assert raw_connection is not None
    with raw_connection.cursor() as raw_cursor:
        with raw_cursor.copy(copy_sql) as copy:
            with stage_file_path.open('r', encoding='utf-8', newline='') as handle:
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


def merge_listenbrainz_partition_to_final(
    plan: FullIngestionPlan,
    partition: FullIngestionPartitionPlan,
    *,
    source_ingestion_run: SourceIngestionRun,
) -> FullIngestionMergeResult:
    with connection.cursor() as cursor:
        cursor.execute(
            f'''
            WITH stage_rows AS (
                SELECT
                    s.*,
                    COALESCE(
                        track_by_mbid.juke_id,
                        track_external.track_id,
                        track_by_spotify.juke_id
                    ) AS track_juke_id
                FROM {LISTENBRAINZ_EVENT_STAGE_TABLE} s
                LEFT JOIN catalog_track track_by_mbid
                    ON s.recording_mbid IS NOT NULL
                    AND track_by_mbid.mbid = s.recording_mbid
                LEFT JOIN catalog_track_external_id track_external
                    ON COALESCE(s.track_identifier_candidates->>'spotify_id', '') <> ''
                    AND track_external.source = 'spotify'
                    AND track_external.external_id = s.track_identifier_candidates->>'spotify_id'
                LEFT JOIN catalog_track track_by_spotify
                    ON COALESCE(s.track_identifier_candidates->>'spotify_id', '') <> ''
                    AND track_by_spotify.spotify_id = s.track_identifier_candidates->>'spotify_id'
                WHERE s.run_id = %s
                  AND s.partition_key = %s
            ),
            inserted_events AS (
                INSERT INTO mlcore_listenbrainz_event_ledger (
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
                    {deterministic_uuid_sql("encode(stage_rows.event_signature, 'hex')")},
                    %s,
                    stage_rows.event_signature,
                    stage_rows.played_at,
                    stage_rows.session_key,
                    stage_rows.track_juke_id,
                    CASE WHEN stage_rows.track_juke_id IS NULL THEN 0 ELSE 1 END,
                    stage_rows.partition_key || ':' || stage_rows.origin || ':' || stage_rows.line_number || ':' || stage_rows.entry_index,
                    NOW()
                FROM stage_rows
                ON CONFLICT (event_signature) DO NOTHING
                RETURNING session_key, track_id, played_at
            ),
            session_track_aggregates AS (
                SELECT
                    session_key,
                    track_id,
                    MIN(played_at) AS first_played_at,
                    MAX(played_at) AS last_played_at,
                    COUNT(*) AS play_count
                FROM inserted_events
                WHERE track_id IS NOT NULL
                GROUP BY session_key, track_id
            ),
            upserted_session_tracks AS (
                INSERT INTO mlcore_listenbrainz_session_track (
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
                            "encode(session_track_aggregates.session_key, 'hex') || ':' || "
                            "session_track_aggregates.track_id::text"
                        )
                    },
                    %s,
                    session_track_aggregates.session_key,
                    session_track_aggregates.track_id,
                    session_track_aggregates.first_played_at,
                    session_track_aggregates.last_played_at,
                    session_track_aggregates.play_count,
                    NOW()
                FROM session_track_aggregates
                ON CONFLICT (session_key, track_id) DO UPDATE
                SET
                    first_played_at = LEAST(
                        mlcore_listenbrainz_session_track.first_played_at,
                        EXCLUDED.first_played_at
                    ),
                    last_played_at = GREATEST(
                        mlcore_listenbrainz_session_track.last_played_at,
                        EXCLUDED.last_played_at
                    ),
                    play_count = mlcore_listenbrainz_session_track.play_count + EXCLUDED.play_count
                RETURNING 1
            ),
            cleared_stage AS (
                DELETE FROM {LISTENBRAINZ_EVENT_STAGE_TABLE}
                WHERE run_id = %s
                  AND partition_key = %s
                RETURNING 1
            )
            SELECT
                COALESCE((SELECT COUNT(*) FROM stage_rows), 0) AS staged_rows,
                COALESCE((SELECT COUNT(*) FROM inserted_events), 0) AS inserted_rows,
                COALESCE((SELECT COUNT(*) FROM inserted_events WHERE track_id IS NOT NULL), 0) AS resolved_rows,
                COALESCE((SELECT COUNT(*) FROM inserted_events WHERE track_id IS NULL), 0) AS unresolved_rows,
                COALESCE((SELECT COUNT(*) FROM upserted_session_tracks), 0) AS session_rows_merged
            ''',
            [
                plan.run_id,
                partition.partition_key,
                str(source_ingestion_run.pk),
                str(source_ingestion_run.pk),
                plan.run_id,
                partition.partition_key,
            ],
        )
        staged_rows, inserted_rows, resolved_rows, unresolved_rows, session_rows_merged = cursor.fetchone()

    return FullIngestionMergeResult(
        partition_key=partition.partition_key,
        rows_merged=int(inserted_rows or 0),
        rows_deduplicated=max(0, int(staged_rows or 0) - int(inserted_rows or 0)),
        rows_resolved=int(resolved_rows or 0),
        rows_unresolved=int(unresolved_rows or 0),
        session_rows_merged=int(session_rows_merged or 0),
    )


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
