import logging

from celery import shared_task

from mlcore.ingestion.listenbrainz import (
    configured_dump_path,
    configured_source_version,
    import_listenbrainz_dump,
)
from mlcore.services.cooccurrence import DEFAULT_BEHAVIOR_SOURCES, train_cooccurrence

logger = logging.getLogger(__name__)


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
    resolved_path = dump_path or configured_dump_path('full')
    if not resolved_path:
        logger.warning('listenbrainz full import skipped: MLCORE_LISTENBRAINZ_FULL_IMPORT_PATH is not set')
        return {'status': 'skipped', 'reason': 'path_not_configured'}

    version = source_version or configured_source_version('full', resolved_path)
    result = import_listenbrainz_dump(resolved_path, source_version=version, import_mode='full')
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
    }


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={'max_retries': 3},
    name='mlcore.tasks.replay_listenbrainz_incremental',
)
def replay_listenbrainz_incremental_task(self, dump_path: str | None = None, source_version: str | None = None):
    resolved_path = dump_path or configured_dump_path('incremental')
    if not resolved_path:
        logger.warning(
            'listenbrainz incremental replay skipped: MLCORE_LISTENBRAINZ_INCREMENTAL_IMPORT_PATH is not set'
        )
        return {'status': 'skipped', 'reason': 'path_not_configured'}

    version = source_version or configured_source_version('incremental', resolved_path)
    result = import_listenbrainz_dump(resolved_path, source_version=version, import_mode='incremental')
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
    }
