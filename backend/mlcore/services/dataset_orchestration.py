from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Protocol

from django.conf import settings
from django.utils import timezone

from mlcore.models import DatasetOrchestrationRun, DatasetShardIngestionRun

logger = logging.getLogger(__name__)

PROGRESS_COUNTER_FIELDS = (
    'source_row_count',
    'imported_row_count',
    'duplicate_row_count',
    'canonicalized_row_count',
    'unresolved_row_count',
    'malformed_row_count',
)


@dataclass(frozen=True)
class DatasetShardSpec:
    key: str
    relative_path: str
    size_bytes: int
    metadata: dict[str, Any]


@dataclass(frozen=True)
class DatasetOrchestrationPlan:
    provider: str
    source_version: str
    manifest_path: str
    output_root: str
    orchestration_path: str
    shard_parallelism: int
    max_shards_per_run: int | None
    shard_count: int
    scheduled_shard_count: int
    total_uncompressed_bytes: int
    scheduled_uncompressed_bytes: int


@dataclass(frozen=True)
class DatasetOrchestrationDocument:
    plan: DatasetOrchestrationPlan
    shards: list[DatasetShardSpec]


@dataclass(frozen=True)
class DatasetMaterializationResult:
    provider: str
    source_version: str
    archive_path: str
    output_root: str
    manifest_path: str
    orchestration_path: str
    shard_count: int
    total_uncompressed_bytes: int
    shard_parallelism: int
    max_shards_per_run: int | None


class DatasetShardOrchestrationService(Protocol):
    provider: str
    import_mode: str

    def configured_archive_path(self) -> str | None:
        ...

    def configured_shard_root(self) -> Path:
        ...

    def materialize_shards(
        self,
        archive_path: str | Path,
        *,
        source_version: str | None = None,
        shard_root: str | Path | None = None,
        force: bool = False,
        shard_parallelism: int | None = None,
        max_shards_per_run: int | None = None,
    ) -> DatasetMaterializationResult:
        ...

    def import_shard(
        self,
        shard_path: str | Path,
        *,
        source_version: str,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ):
        ...


def configured_dataset_shard_parallelism() -> int:
    return max(1, int(getattr(settings, 'MLCORE_DATASET_SHARD_PARALLELISM', 1)))


def configured_celery_worker_total_slots() -> int:
    return max(1, int(getattr(settings, 'CELERY_WORKER_TOTAL_SLOTS', 1)))


def validate_dataset_worker_capacity(shard_parallelism: int | None = None) -> int:
    resolved_shard_parallelism = max(1, int(shard_parallelism or configured_dataset_shard_parallelism()))
    total_slots = configured_celery_worker_total_slots()
    minimum_total_slots = resolved_shard_parallelism + 1
    if total_slots < minimum_total_slots:
        raise ValueError(
            'Dataset orchestration requires CELERY_WORKER_TOTAL_SLOTS >= '
            f'MLCORE_DATASET_SHARD_PARALLELISM + 1; got total_slots={total_slots} '
            f'and shard_parallelism={resolved_shard_parallelism}'
        )
    return resolved_shard_parallelism


def configured_dataset_max_shards_per_run() -> int | None:
    value = int(getattr(settings, 'MLCORE_DATASET_MAX_SHARDS_PER_RUN', 0))
    return value if value > 0 else None


def configured_dataset_stale_timeout_seconds() -> int:
    return int(getattr(settings, 'MLCORE_DATASET_ORCHESTRATION_STALE_TIMEOUT_SECONDS', 60 * 30))


def configured_dataset_poll_seconds() -> float:
    return float(getattr(settings, 'MLCORE_DATASET_ORCHESTRATION_POLL_SECONDS', '5'))


def configured_dataset_orchestration_log_seconds() -> float:
    return float(getattr(settings, 'MLCORE_DATASET_ORCHESTRATION_LOG_SECONDS', '300'))


def load_dataset_orchestration_document(orchestration_path: str | Path) -> DatasetOrchestrationDocument:
    path = Path(orchestration_path)
    payload = json.loads(path.read_text(encoding='utf-8'))
    plan = DatasetOrchestrationPlan(
        provider=str(payload['provider']),
        source_version=str(payload['source_version']),
        manifest_path=str(payload['manifest_path']),
        output_root=str(payload['output_root']),
        orchestration_path=str(payload.get('orchestration_path') or path),
        shard_parallelism=int(payload['shard_parallelism']),
        max_shards_per_run=(
            int(payload['max_shards_per_run'])
            if payload.get('max_shards_per_run') not in (None, '', 0)
            else None
        ),
        shard_count=int(payload['shard_count']),
        scheduled_shard_count=int(payload['scheduled_shard_count']),
        total_uncompressed_bytes=int(payload['total_uncompressed_bytes']),
        scheduled_uncompressed_bytes=int(payload['scheduled_uncompressed_bytes']),
    )
    shards = [
        DatasetShardSpec(
            key=str(shard['relative_path']),
            relative_path=str(shard['relative_path']),
            size_bytes=int(shard['size_bytes']),
            metadata=dict(shard),
        )
        for shard in payload['shards']
    ]
    return DatasetOrchestrationDocument(plan=plan, shards=shards)


def aggregate_dataset_progress(
    plan: DatasetOrchestrationPlan,
    shard_snapshots: list[dict[str, Any]],
) -> dict[str, Any]:
    aggregate = {
        'provider': plan.provider,
        'source_version': plan.source_version,
        'shard_parallelism': plan.shard_parallelism,
        'max_shards_per_run': plan.max_shards_per_run,
        'shard_count': plan.shard_count,
        'scheduled_shard_count': plan.scheduled_shard_count,
        'completed_shards': 0,
        'running_shards': 0,
        'failed_shards': 0,
        'pending_shards': 0,
        'scheduled_uncompressed_bytes': plan.scheduled_uncompressed_bytes,
        'completed_uncompressed_bytes': 0,
    }
    for field in PROGRESS_COUNTER_FIELDS:
        aggregate[field] = 0

    for snapshot in shard_snapshots:
        status = str(snapshot.get('status') or 'pending')
        if status == 'succeeded':
            aggregate['completed_shards'] += 1
            aggregate['completed_uncompressed_bytes'] += int(snapshot.get('size_bytes') or 0)
        elif status == 'running':
            aggregate['running_shards'] += 1
        elif status == 'failed':
            aggregate['failed_shards'] += 1
        else:
            aggregate['pending_shards'] += 1
        for field in PROGRESS_COUNTER_FIELDS:
            aggregate[field] += int(snapshot.get(field) or 0)

    return aggregate


def get_dataset_orchestration_service(provider: str) -> DatasetShardOrchestrationService:
    normalized = str(provider or '').strip().casefold()
    if normalized == 'listenbrainz':
        from mlcore.services.listenbrainz_shards import LISTENBRAINZ_SHARD_SERVICE

        return LISTENBRAINZ_SHARD_SERVICE
    raise ValueError(f"Unsupported dataset provider '{provider}'")


def get_or_create_dataset_orchestration_run(
    document: DatasetOrchestrationDocument,
) -> DatasetOrchestrationRun:
    run, created = DatasetOrchestrationRun.objects.get_or_create(
        provider=document.plan.provider,
        source_version=document.plan.source_version,
        orchestration_path=document.plan.orchestration_path,
        defaults={
            'import_mode': 'full',
            'manifest_path': document.plan.manifest_path,
            'output_root': document.plan.output_root,
            'shard_parallelism': document.plan.shard_parallelism,
            'max_shards_per_run': document.plan.max_shards_per_run,
            'shard_count': document.plan.shard_count,
            'scheduled_shard_count': document.plan.scheduled_shard_count,
            'metadata': {
                'scheduled_uncompressed_bytes': document.plan.scheduled_uncompressed_bytes,
                'total_uncompressed_bytes': document.plan.total_uncompressed_bytes,
            },
        },
    )
    if created:
        return run

    run.import_mode = 'full'
    run.manifest_path = document.plan.manifest_path
    run.output_root = document.plan.output_root
    run.shard_parallelism = document.plan.shard_parallelism
    run.max_shards_per_run = document.plan.max_shards_per_run
    run.shard_count = document.plan.shard_count
    run.scheduled_shard_count = document.plan.scheduled_shard_count
    run.metadata = {
        **run.metadata,
        'scheduled_uncompressed_bytes': document.plan.scheduled_uncompressed_bytes,
        'total_uncompressed_bytes': document.plan.total_uncompressed_bytes,
    }
    run.save(
        update_fields=[
            'import_mode',
            'manifest_path',
            'output_root',
            'shard_parallelism',
            'max_shards_per_run',
            'shard_count',
            'scheduled_shard_count',
            'metadata',
        ]
    )
    return run


def ensure_dataset_shard_runs(
    orchestration_run: DatasetOrchestrationRun,
    document: DatasetOrchestrationDocument,
) -> None:
    expected_keys = {shard.key for shard in document.shards}
    obsolete_rows = orchestration_run.shard_runs.exclude(shard_key__in=expected_keys)
    if obsolete_rows.filter(status='running').exists():
        raise ValueError('Cannot replace running shard rows while the orchestration run is active')
    if obsolete_rows.exists():
        obsolete_rows.delete()

    existing_keys = set(
        orchestration_run.shard_runs.values_list('shard_key', flat=True)
    )
    missing_rows = []
    for shard in document.shards:
        if shard.key in existing_keys:
            continue
        missing_rows.append(
            DatasetShardIngestionRun(
                orchestration_run=orchestration_run,
                provider=document.plan.provider,
                import_mode='full',
                source_version=document.plan.source_version,
                shard_key=shard.key,
                shard_path=str(Path(document.plan.output_root) / shard.relative_path),
                metadata={
                    'relative_path': shard.relative_path,
                    'size_bytes': shard.size_bytes,
                    **shard.metadata,
                },
            )
        )
    if missing_rows:
        DatasetShardIngestionRun.objects.bulk_create(missing_rows)


def expire_stale_dataset_shard_runs(
    orchestration_run: DatasetOrchestrationRun,
) -> list[DatasetShardIngestionRun]:
    now = timezone.now()
    cutoff = now - timedelta(seconds=configured_dataset_stale_timeout_seconds())
    stale_runs: list[DatasetShardIngestionRun] = []
    for shard_run in orchestration_run.shard_runs.filter(status='running').select_related('source_ingestion_run'):
        progress_at = _latest_progress_timestamp(shard_run)
        if progress_at is None or progress_at > cutoff:
            continue
        shard_run.status = 'failed'
        shard_run.completed_at = now
        shard_run.last_error = (
            f'Stale shard worker marked failed after no progress since {progress_at.isoformat()}'
        )
        shard_run.metadata = {
            **shard_run.metadata,
            'stale_marked_at': now.isoformat(),
            'last_progress_at': progress_at.isoformat(),
        }
        shard_run.save(update_fields=['status', 'completed_at', 'last_error', 'metadata'])
        if shard_run.source_ingestion_run and shard_run.source_ingestion_run.status in ('pending', 'running'):
            source_run = shard_run.source_ingestion_run
            source_run.status = 'failed'
            source_run.completed_at = now
            source_run.last_error = (
                f'Stale shard import marked failed after no progress since {progress_at.isoformat()}'
            )
            source_run.metadata = {
                **source_run.metadata,
                'stage': 'failed',
                'stale_marked_at': now.isoformat(),
            }
            source_run.save(update_fields=['status', 'completed_at', 'last_error', 'metadata'])
        stale_runs.append(shard_run)
    return stale_runs


def dispatch_dataset_shard_tasks(
    orchestration_run: DatasetOrchestrationRun,
    document: DatasetOrchestrationDocument,
    *,
    orchestration_session_id: str,
    dispatch_shard_task: Callable[[str, str, str], Any],
) -> list[DatasetShardIngestionRun]:
    running_count = orchestration_run.shard_runs.filter(status='running').count()
    available_slots = max(0, orchestration_run.shard_parallelism - running_count)
    if available_slots <= 0:
        return []

    queued: list[DatasetShardIngestionRun] = []
    shard_runs = list(orchestration_run.shard_runs.all().order_by('shard_key'))
    for shard_run in shard_runs:
        if len(queued) >= available_slots:
            break
        if shard_run.status == 'succeeded':
            continue
        if shard_run.status == 'running':
            continue
        if shard_run.status == 'failed':
            same_session = shard_run.metadata.get('orchestrator_session_id') == orchestration_session_id
            stale_marked = bool(shard_run.metadata.get('stale_marked_at'))
            if same_session and not stale_marked:
                continue

        dispatch_result = dispatch_shard_task(
            orchestration_run.provider,
            str(orchestration_run.pk),
            str(shard_run.pk),
        )
        task_id = getattr(dispatch_result, 'id', '')
        dispatched_at = timezone.now().isoformat()
        shard_run.status = 'running'
        shard_run.task_id = task_id
        shard_run.completed_at = None
        shard_run.last_error = ''
        shard_run.metadata = {
            **shard_run.metadata,
            'orchestrator_session_id': orchestration_session_id,
            'dispatched_at': dispatched_at,
            'last_progress_at': dispatched_at,
            'dispatch_count': int(shard_run.metadata.get('dispatch_count') or 0) + 1,
        }
        shard_run.metadata.pop('stale_marked_at', None)
        shard_run.save(update_fields=['status', 'task_id', 'completed_at', 'last_error', 'metadata'])
        queued.append(shard_run)
    return queued


def refresh_dataset_orchestration_run(
    orchestration_run: DatasetOrchestrationRun,
    document: DatasetOrchestrationDocument,
) -> dict[str, Any]:
    shard_snapshots = list(
        orchestration_run.shard_runs.values(
            'status',
            'metadata',
            'source_row_count',
            'imported_row_count',
            'duplicate_row_count',
            'canonicalized_row_count',
            'unresolved_row_count',
            'malformed_row_count',
        )
    )
    for snapshot in shard_snapshots:
        metadata = snapshot.pop('metadata', {}) or {}
        snapshot['size_bytes'] = int(metadata.get('size_bytes') or 0)
    aggregate = aggregate_dataset_progress(document.plan, shard_snapshots)
    final_status = 'running'
    if aggregate['completed_shards'] >= document.plan.scheduled_shard_count:
        final_status = 'succeeded'
    elif aggregate['failed_shards'] > 0 and aggregate['running_shards'] == 0 and aggregate['pending_shards'] == 0:
        final_status = 'failed'

    completed_at = timezone.now() if final_status in ('succeeded', 'failed') else None
    orchestration_run.status = final_status
    orchestration_run.completed_shard_count = aggregate['completed_shards']
    orchestration_run.failed_shard_count = aggregate['failed_shards']
    for field in PROGRESS_COUNTER_FIELDS:
        setattr(orchestration_run, field, aggregate[field])
    orchestration_run.completed_at = completed_at
    orchestration_run.metadata = {
        **orchestration_run.metadata,
        'last_progress_at': timezone.now().isoformat(),
        'running_shards': aggregate['running_shards'],
        'pending_shards': aggregate['pending_shards'],
        'scheduled_uncompressed_bytes': document.plan.scheduled_uncompressed_bytes,
        'total_uncompressed_bytes': document.plan.total_uncompressed_bytes,
    }
    orchestration_run.save(
        update_fields=[
            'status',
            'completed_shard_count',
            'failed_shard_count',
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
    return {
        **aggregate,
        'status': final_status,
        'orchestration_run_id': str(orchestration_run.pk),
    }


def _log_dataset_orchestration_progress(
    aggregate: dict[str, Any],
    *,
    log_reason: str,
) -> None:
    scheduled_shards = max(1, int(aggregate.get('scheduled_shard_count') or 0))
    scheduled_bytes = max(1, int(aggregate.get('scheduled_uncompressed_bytes') or 0))
    shard_pct = (100.0 * int(aggregate.get('completed_shards') or 0)) / scheduled_shards
    byte_pct = (100.0 * int(aggregate.get('completed_uncompressed_bytes') or 0)) / scheduled_bytes
    logger.info(
        'dataset orchestration progress provider=%s source_version=%s reason=%s status=%s '
        'shards=%d/%d running=%d pending=%d failed=%d '
        'shard_pct=%.2f byte_pct=%.2f bytes=%d/%d '
        'rows=%d imported=%d duplicates=%d unresolved=%d malformed=%d',
        aggregate['provider'],
        aggregate['source_version'],
        log_reason,
        aggregate['status'],
        int(aggregate.get('completed_shards') or 0),
        scheduled_shards,
        int(aggregate.get('running_shards') or 0),
        int(aggregate.get('pending_shards') or 0),
        int(aggregate.get('failed_shards') or 0),
        shard_pct,
        byte_pct,
        int(aggregate.get('completed_uncompressed_bytes') or 0),
        scheduled_bytes,
        int(aggregate.get('source_row_count') or 0),
        int(aggregate.get('imported_row_count') or 0),
        int(aggregate.get('duplicate_row_count') or 0),
        int(aggregate.get('unresolved_row_count') or 0),
        int(aggregate.get('malformed_row_count') or 0),
    )


def run_dataset_orchestration_loop(
    *,
    provider: str,
    orchestration_path: str | Path,
    orchestration_session_id: str,
    dispatch_shard_task: Callable[[str, str, str], Any],
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    document = load_dataset_orchestration_document(orchestration_path)
    if document.plan.provider != provider:
        raise ValueError(
            f"Orchestration provider mismatch: expected '{provider}' found '{document.plan.provider}'"
        )
    validate_dataset_worker_capacity(document.plan.shard_parallelism)
    orchestration_run = get_or_create_dataset_orchestration_run(document)
    ensure_dataset_shard_runs(orchestration_run, document)

    orchestration_run.status = 'running'
    orchestration_run.completed_at = None
    orchestration_run.last_error = ''
    orchestration_run.metadata = {
        **orchestration_run.metadata,
        'active_session_id': orchestration_session_id,
        'last_progress_at': timezone.now().isoformat(),
    }
    orchestration_run.save(update_fields=['status', 'completed_at', 'last_error', 'metadata'])
    last_logged_at = 0.0
    log_interval_seconds = max(1.0, configured_dataset_orchestration_log_seconds())

    while True:
        orchestration_run.refresh_from_db()
        expire_stale_dataset_shard_runs(orchestration_run)
        dispatch_dataset_shard_tasks(
            orchestration_run,
            document,
            orchestration_session_id=orchestration_session_id,
            dispatch_shard_task=dispatch_shard_task,
        )
        orchestration_run.refresh_from_db()
        aggregate = refresh_dataset_orchestration_run(orchestration_run, document)
        if progress_callback is not None:
            progress_callback(aggregate)
        now_monotonic = time.monotonic()
        if last_logged_at == 0.0 or now_monotonic - last_logged_at >= log_interval_seconds:
            _log_dataset_orchestration_progress(aggregate, log_reason='heartbeat')
            last_logged_at = now_monotonic
        if aggregate['status'] in ('succeeded', 'failed'):
            if now_monotonic != last_logged_at:
                _log_dataset_orchestration_progress(aggregate, log_reason='final')
            return aggregate
        time.sleep(configured_dataset_poll_seconds())


def _metadata_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed


def _latest_progress_timestamp(shard_run: DatasetShardIngestionRun) -> datetime | None:
    timestamps = [
        _metadata_timestamp(shard_run.metadata.get('last_progress_at')),
        _metadata_timestamp(shard_run.metadata.get('dispatched_at')),
    ]
    if shard_run.source_ingestion_run is not None:
        timestamps.append(_metadata_timestamp(shard_run.source_ingestion_run.metadata.get('last_progress_at')))
    timestamps = [value for value in timestamps if value is not None]
    if not timestamps:
        return None
    return max(timestamps)
