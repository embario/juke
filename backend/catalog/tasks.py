from __future__ import annotations

import logging

from celery import shared_task

from catalog.services.catalog_crawl import crawl_catalog
from catalog.services.featured_genres import refresh_featured_genres
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


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={'max_retries': 3},
    name='catalog.tasks.refresh_featured_genres',
)
def refresh_featured_genres_task(self):
    payload = refresh_featured_genres(enforce_budget=False)
    logger.info('Featured genres refresh task finished: %s genres', len(payload))
    return {'count': len(payload)}


@shared_task(
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_kwargs={'max_retries': 3},
    name='catalog.tasks.crawl_catalog',
)
def crawl_catalog_task(self):
    result = crawl_catalog()
    logger.info(
        'Catalog crawl task finished: artists_created=%d albums_created=%d '
        'tracks_created=%d failed=%d',
        result.artists_created, result.albums_created,
        result.tracks_created, len(result.failed_artist_ids),
    )
    return {
        'artists_created': result.artists_created,
        'albums_created': result.albums_created,
        'tracks_created': result.tracks_created,
        'artists_skipped': result.artists_skipped,
        'albums_skipped': result.albums_skipped,
        'tracks_skipped': result.tracks_skipped,
        'failed_artist_ids': result.failed_artist_ids,
        'failed_track_ids': result.failed_track_ids,
        'crawled_at': result.crawled_at,
    }
