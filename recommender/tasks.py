from __future__ import annotations

import logging

from celery import shared_task

from catalog.models import Artist, Album, Track
from recommender.models import ArtistEmbedding, AlbumEmbedding, TrackEmbedding
from recommender.services.client import generate_embedding

logger = logging.getLogger(__name__)

MODEL_VERSION = 'v1.0.0'


def _upsert_embedding(instance, payload):
    instance.vector = payload.get('vector', [])
    instance.model_version = payload.get('model_version', MODEL_VERSION)
    instance.quality_score = payload.get('quality', 0.0)
    instance.metadata = payload.get('metadata', {})
    instance.save()
    return instance


def _embed(resource_type: str, attributes: dict) -> dict:
    return generate_embedding(resource_type, attributes)


@shared_task
def sync_artist_embedding(artist_id: int):
    artist = Artist.objects.get(pk=artist_id)
    payload = _embed('artist', {'name': artist.name, 'spotify_id': artist.spotify_id})
    embedding, _ = ArtistEmbedding.objects.get_or_create(artist=artist, defaults={'model_version': MODEL_VERSION})
    _upsert_embedding(embedding, payload)
    logger.info('Artist embedding synced for %s', artist.name)


@shared_task
def sync_album_embedding(album_id: int):
    album = Album.objects.get(pk=album_id)
    payload = _embed('album', {
        'name': album.name,
        'spotify_id': album.spotify_id,
        'artists': list(album.artists.values_list('name', flat=True)),
    })
    embedding, _ = AlbumEmbedding.objects.get_or_create(album=album, defaults={'model_version': MODEL_VERSION})
    _upsert_embedding(embedding, payload)
    logger.info('Album embedding synced for %s', album.name)


@shared_task
def sync_track_embedding(track_id: int):
    track = Track.objects.get(pk=track_id)
    payload = _embed('track', {
        'name': track.name,
        'spotify_id': track.spotify_id,
        'album': track.album.name,
        'artists': list(track.album.artists.values_list('name', flat=True)),
    })
    embedding, _ = TrackEmbedding.objects.get_or_create(track=track, defaults={'model_version': MODEL_VERSION})
    _upsert_embedding(embedding, payload)
    logger.info('Track embedding synced for %s', track.name)
