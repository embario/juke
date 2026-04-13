import logging
from uuid import uuid4

from celery import shared_task
from django.utils import timezone

from mlcore.ingestion.listenbrainz import (
    configured_dump_path,
    configured_source_version,
    import_listenbrainz_dump,
)
from mlcore.models import DatasetShardIngestionRun, SourceIngestionRun
from mlcore.services.cooccurrence import DEFAULT_BEHAVIOR_SOURCES, train_cooccurrence
from mlcore.services.dataset_orchestration import (
    PROGRESS_COUNTER_FIELDS,
    get_dataset_orchestration_service,
    run_dataset_orchestration_loop,
)
from mlcore.services.full_ingestion import full_ingestion_conflict_metadata
from mlcore.services.listenbrainz_source import sync_listenbrainz_remote_dumps

logger = logging.getLogger(__name__)


def _task_progress_callback(task, *, import_mode: str, resolved_path: str, source_version: str):
    base_meta = {
        'status': 'running',
        'source': 'listenbrainz',
        'import_mode': import_mode,
        'source_version': source_version,
        'raw_path': resolved_path,
        'source_row_count': 0,
        'imported_row_count': 0,
        'duplicate_row_count': 0,
        'canonicalized_row_count': 0,
        'unresolved_row_count': 0,
        'malformed_row_count': 0,
    }
    task.update_state(state='PROGRESS', meta=base_meta)

    def _report(meta):
        task.update_state(state='PROGRESS', meta={**base_meta, **meta})

    return _report


def _persist_dataset_shard_progress(
    shard_run_id: str,
    *,
    status: str,
    source_ingestion_run_id: str | None = None,
    last_error: str | None = None,
    extra_meta: dict[str, object] | None = None,
) -> dict[str, object]:
    shard_run = DatasetShardIngestionRun.objects.select_related('orchestration_run').get(pk=shard_run_id)
    payload = extra_meta or {}
    for field in PROGRESS_COUNTER_FIELDS:
        if field in payload:
            setattr(shard_run, field, int(payload.get(field) or 0))
    shard_run.status = status
    if source_ingestion_run_id:
        shard_run.source_ingestion_run_id = source_ingestion_run_id
    if last_error is not None:
        shard_run.last_error = last_error
    if status in ('succeeded', 'failed'):
        shard_run.completed_at = timezone.now()
    shard_run.metadata = {
        **shard_run.metadata,
        **payload,
        'last_progress_at': timezone.now().isoformat(),
    }
    update_fields = [
        'status',
        'source_row_count',
        'imported_row_count',
        'duplicate_row_count',
        'canonicalized_row_count',
        'unresolved_row_count',
        'malformed_row_count',
        'metadata',
    ]
    if source_ingestion_run_id:
        update_fields.append('source_ingestion_run')
    if last_error is not None:
        update_fields.append('last_error')
    if status in ('succeeded', 'failed'):
        update_fields.append('completed_at')
    shard_run.save(update_fields=update_fields)
    return {
        'provider': shard_run.provider,
        'source_version': shard_run.source_version,
        'shard_key': shard_run.shard_key,
        'status': shard_run.status,
        'orchestration_run_id': str(shard_run.orchestration_run_id),
        **{field: getattr(shard_run, field) for field in PROGRESS_COUNTER_FIELDS},
    }


def _lookup_latest_source_ingestion_run(*, provider: str, source_version: str, shard_path: str) -> SourceIngestionRun | None:
    return (
        SourceIngestionRun.objects.filter(
            source=provider,
            source_version=source_version,
            raw_path=shard_path,
        )
        .order_by('-started_at')
        .first()
    )


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={'max_retries': 3},
    name='mlcore.tasks.train_cooccurrence',
)
def train_cooccurrence_task(
    self,
    *,
    split: str = 'train',
    split_buckets: int = 10,
    sources: list[str] | None = None,
):
    result = train_cooccurrence(split=split, split_buckets=split_buckets, sources=sources)
    effective_sources = list(sources or DEFAULT_BEHAVIOR_SOURCES)
    logger.info(
        'train_cooccurrence task finished: split=%s pairs=%d baskets=%d items=%d skipped=%d',
        split,
        result.pairs_written,
        result.baskets_processed,
        result.items_seen,
        result.baskets_skipped,
    )
    return {
        'split': split,
        'split_buckets': split_buckets,
        'sources': effective_sources,
        'pairs_written': result.pairs_written,
        'baskets_processed': result.baskets_processed,
        'baskets_skipped': result.baskets_skipped,
        'items_seen': result.items_seen,
        'training_hash': result.training_hash,
        'source_row_count': result.source_row_count,
        'training_run_id': str(result.training_run_id) if result.training_run_id else None,
    }


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={'max_retries': 3},
    name='mlcore.tasks.import_listenbrainz_full',
)
def import_listenbrainz_full_task(self, dump_path: str | None = None, source_version: str | None = None):
    lease_conflict = full_ingestion_conflict_metadata('listenbrainz')
    if lease_conflict is not None:
        logger.warning(
            'listenbrainz full import skipped because full ingestion run %s owns the provider lease',
            lease_conflict['lease_run_id'],
        )
        return {'status': 'skipped', **lease_conflict}

    resolved_path = dump_path or configured_dump_path('full')
    if not resolved_path:
        logger.warning('listenbrainz full import skipped: MLCORE_LISTENBRAINZ_FULL_IMPORT_PATH is not set')
        return {'status': 'skipped', 'reason': 'path_not_configured'}

    version = source_version or configured_source_version('full', resolved_path)
    result = import_listenbrainz_dump(
        resolved_path,
        source_version=version,
        import_mode='full',
        progress_callback=_task_progress_callback(
            self,
            import_mode='full',
            resolved_path=resolved_path,
            source_version=version,
        ),
    )
    return {
        'status': result.status,
        'run_id': str(result.run_id),
        'source_row_count': result.source_row_count,
        'imported_row_count': result.imported_row_count,
        'duplicate_row_count': result.duplicate_row_count,
        'canonicalized_row_count': result.canonicalized_row_count,
        'unresolved_row_count': result.unresolved_row_count,
        'malformed_row_count': result.malformed_row_count,
        'checksum': result.checksum,
        'fingerprint': result.fingerprint,
    }


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={'max_retries': 3},
    name='mlcore.tasks.replay_listenbrainz_incremental',
)
def replay_listenbrainz_incremental_task(self, dump_path: str | None = None, source_version: str | None = None):
    lease_conflict = full_ingestion_conflict_metadata('listenbrainz')
    if lease_conflict is not None:
        logger.warning(
            'listenbrainz incremental replay skipped because full ingestion run %s owns the provider lease',
            lease_conflict['lease_run_id'],
        )
        return {'status': 'skipped', **lease_conflict}

    resolved_path = dump_path or configured_dump_path('incremental')
    if not resolved_path:
        logger.warning(
            'listenbrainz incremental replay skipped: MLCORE_LISTENBRAINZ_INCREMENTAL_IMPORT_PATH is not set'
        )
        return {'status': 'skipped', 'reason': 'path_not_configured'}

    version = source_version or configured_source_version('incremental', resolved_path)
    result = import_listenbrainz_dump(
        resolved_path,
        source_version=version,
        import_mode='incremental',
        progress_callback=_task_progress_callback(
            self,
            import_mode='incremental',
            resolved_path=resolved_path,
            source_version=version,
        ),
    )
    return {
        'status': result.status,
        'run_id': str(result.run_id),
        'source_row_count': result.source_row_count,
        'imported_row_count': result.imported_row_count,
        'duplicate_row_count': result.duplicate_row_count,
        'canonicalized_row_count': result.canonicalized_row_count,
        'unresolved_row_count': result.unresolved_row_count,
        'malformed_row_count': result.malformed_row_count,
        'checksum': result.checksum,
        'fingerprint': result.fingerprint,
    }


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={'max_retries': 3},
    name='mlcore.tasks.import_dataset_shard',
)
def import_dataset_shard_task(
    self,
    *,
    provider: str,
    orchestration_run_id: str,
    shard_run_id: str,
):
    service = get_dataset_orchestration_service(provider)
    shard_run = DatasetShardIngestionRun.objects.select_related('orchestration_run').get(pk=shard_run_id)
    _persist_dataset_shard_progress(
        shard_run_id,
        status='running',
        extra_meta={
            'task_id': self.request.id or '',
            'orchestration_run_id': orchestration_run_id,
            'shard_path': shard_run.shard_path,
            'phase': 'starting',
        },
    )

    def _report(meta):
        snapshot = _persist_dataset_shard_progress(
            shard_run_id,
            status='running',
            extra_meta=meta,
        )
        self.update_state(state='PROGRESS', meta=snapshot)

    try:
        result = service.import_shard(
            shard_run.shard_path,
            source_version=shard_run.source_version,
            progress_callback=_report,
        )
        snapshot = _persist_dataset_shard_progress(
            shard_run_id,
            status=result.status,
            source_ingestion_run_id=str(result.run_id),
            extra_meta={
                'phase': 'completed',
                'checksum': result.checksum,
                'fingerprint': result.fingerprint,
                **{field: getattr(result, field) for field in PROGRESS_COUNTER_FIELDS},
            },
        )
        return {
            **snapshot,
            'run_id': str(result.run_id),
            'checksum': result.checksum,
            'fingerprint': result.fingerprint,
        }
    except Exception as exc:
        latest_source_run = _lookup_latest_source_ingestion_run(
            provider=provider,
            source_version=shard_run.source_version,
            shard_path=shard_run.shard_path,
        )
        snapshot = _persist_dataset_shard_progress(
            shard_run_id,
            status='failed',
            source_ingestion_run_id=str(latest_source_run.pk) if latest_source_run else None,
            last_error=str(exc),
            extra_meta={'phase': 'failed'},
        )
        self.update_state(state='FAILURE', meta=snapshot)
        raise


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={'max_retries': 3},
    name='mlcore.tasks.run_dataset_orchestration',
)
def run_dataset_orchestration_task(
    self,
    *,
    provider: str,
    orchestration_path: str,
):
    session_id = self.request.id or str(uuid4())

    def _dispatch(shard_provider: str, orchestration_run_id: str, shard_run_id: str):
        return import_dataset_shard_task.apply_async(
            kwargs={
                'provider': shard_provider,
                'orchestration_run_id': orchestration_run_id,
                'shard_run_id': shard_run_id,
            },
            queue='mlcore',
        )

    def _report(meta):
        self.update_state(state='PROGRESS', meta=meta)

    result = run_dataset_orchestration_loop(
        provider=provider,
        orchestration_path=orchestration_path,
        orchestration_session_id=session_id,
        dispatch_shard_task=_dispatch,
        progress_callback=_report,
    )
    logger.info(
        'dataset orchestration finished provider=%s source_version=%s status=%s completed=%d failed=%d running=%d pending=%d',
        provider,
        result['source_version'],
        result['status'],
        result['completed_shards'],
        result['failed_shards'],
        result['running_shards'],
        result['pending_shards'],
    )
    return result


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={'max_retries': 3},
    name='mlcore.tasks.sync_listenbrainz_remote',
)
def sync_listenbrainz_remote_task(self, *, max_incrementals_per_run: int | None = None):
    logger.info(
        'sync_listenbrainz_remote task starting max_incrementals_per_run=%s',
        max_incrementals_per_run,
    )
    progress_callback = _task_progress_callback(
        self,
        import_mode='',
        resolved_path='',
        source_version='',
    )
    progress_callback(
        {
            'status': 'running',
            'sync_phase': 'starting',
            'max_incrementals_per_run': max_incrementals_per_run,
        }
    )
    result = sync_listenbrainz_remote_dumps(
        max_incrementals_per_run=max_incrementals_per_run,
        progress_callback=progress_callback,
    )
    logger.info(
        'sync_listenbrainz_remote task finished status=%s full=%s incrementals=%d downloads=%d skipped=%d',
        result.status,
        result.full_source_version or '-',
        len(result.incremental_source_versions),
        len(result.downloaded_paths),
        len(result.skipped_source_versions),
    )
    return {
        'status': result.status,
        'policy_classification': result.policy_classification,
        'full_source_version': result.full_source_version,
        'incremental_source_versions': result.incremental_source_versions,
        'downloaded_paths': result.downloaded_paths,
        'skipped_source_versions': result.skipped_source_versions,
    }
