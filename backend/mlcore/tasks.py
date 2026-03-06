import logging

from celery import shared_task

from mlcore.services.cooccurrence import train_cooccurrence

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={'max_retries': 3},
    name='mlcore.tasks.train_cooccurrence',
)
def train_cooccurrence_task(self):
    result = train_cooccurrence()
    logger.info(
        'train_cooccurrence task finished: pairs=%d baskets=%d items=%d skipped=%d',
        result.pairs_written, result.baskets_processed, result.items_seen, result.baskets_skipped,
    )
    return {
        'pairs_written': result.pairs_written,
        'baskets_processed': result.baskets_processed,
        'baskets_skipped': result.baskets_skipped,
        'items_seen': result.items_seen,
    }
