from __future__ import annotations

import logging

from celery import shared_task

from catalog.services.genre_sync import sync_spotify_genres

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={'max_retries': 3},
    name='catalog.tasks.sync_spotify_genres',
)
def sync_spotify_genres_task(self):
    result = sync_spotify_genres()
    logger.info('Genre sync task finished: %s', result)
    return {
        'created': result.created,
        'updated': result.updated,
        'total': result.total,
        'source': result.source,
        'synced_at': result.synced_at,
    }
