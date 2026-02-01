from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Sequence

from django.conf import settings

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from catalog import spotify_stub
from catalog.models import Artist, Track
from recommender.models import TrackAudioFeatures

logger = logging.getLogger(__name__)

# Spotify audio_features endpoint accepts up to 50 IDs per call.
_BATCH_SIZE = 50

# Field names on TrackAudioFeatures that map directly from the Spotify payload.
_AUDIO_FIELDS = (
    'energy',
    'valence',
    'tempo',
    'key',
    'mode',
    'danceability',
    'acousticness',
    'instrumentalness',
    'liveness',
    'speechiness',
    'loudness',
    'time_signature',
)


@dataclass
class IngestResult:
    ingested: int = 0
    skipped: int = 0
    failed: int = 0
    failed_track_ids: list[str] = field(default_factory=list)


_spotify_client: spotipy.Spotify | None = None


def _get_spotify_client() -> spotipy.Spotify:
    global _spotify_client
    if _spotify_client is None:
        _spotify_client = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials())
    return _spotify_client


def _fetch_audio_features(track_ids: Sequence[str]) -> list[dict]:
    """Call Spotify (or stub) for a batch of track IDs."""
    if getattr(settings, 'SPOTIFY_USE_STUB_DATA', False):
        return spotify_stub.audio_features(list(track_ids))
    return _get_spotify_client().audio_features(list(track_ids)) or []


def _upsert_audio_features(track: Track, payload: dict) -> None:
    defaults = {f: payload[f] for f in _AUDIO_FIELDS}
    TrackAudioFeatures.objects.update_or_create(track=track, defaults=defaults)


def ingest_training_data() -> IngestResult:
    """Crawl the catalog in deterministic DFS order and pull audio features.

    Order: artists sorted by (name, spotify_id), then for each artist all albums
    sorted by name, then tracks within each album sorted by track_number.

    Tracks that already have a TrackAudioFeatures row are skipped, giving free
    resume semantics on restart without a cursor table.
    """
    result = IngestResult()

    artists = Artist.objects.order_by('name', 'spotify_id')

    for artist in artists:
        logger.info('ingest: artist started — %s', artist.name)

        albums = artist.albums.order_by('name')
        for album in albums:
            logger.info('ingest: album started — %s / %s', artist.name, album.name)

            tracks = list(album.tracks.order_by('track_number'))

            # Partition into tracks that need ingestion vs those already done.
            pending: list[Track] = []
            for track in tracks:
                if TrackAudioFeatures.objects.filter(track=track).exists():
                    result.skipped += 1
                else:
                    pending.append(track)

            # Process pending tracks in batches of _BATCH_SIZE.
            for batch_start in range(0, len(pending), _BATCH_SIZE):
                batch = pending[batch_start:batch_start + _BATCH_SIZE]
                batch_ids = [t.spotify_id for t in batch]
                id_to_track = {t.spotify_id: t for t in batch}

                try:
                    features_list = _fetch_audio_features(batch_ids)
                except Exception:
                    failed_names = [
                        f"{id_to_track[sid].name} ({sid})" for sid in batch_ids
                    ]
                    logger.exception(
                        'ingest: batch fetch failed for album %s / %s: [%s]',
                        artist.name, album.name, ', '.join(failed_names),
                    )
                    result.failed += len(batch)
                    result.failed_track_ids.extend(batch_ids)
                    continue

                # Index the response by track ID so we can match back.
                features_by_id = {item['id']: item for item in features_list if item}

                for track in batch:
                    payload = features_by_id.get(track.spotify_id)
                    if payload is None:
                        logger.warning(
                            'ingest: no features returned for track %s (%s)',
                            track.name, track.spotify_id,
                        )
                        result.failed += 1
                        result.failed_track_ids.append(track.spotify_id)
                        continue

                    try:
                        _upsert_audio_features(track, payload)
                        result.ingested += 1
                    except Exception:
                        logger.exception(
                            'ingest: upsert failed for track %s (%s)',
                            track.name, track.spotify_id,
                        )
                        result.failed += 1
                        result.failed_track_ids.append(track.spotify_id)

            logger.info(
                'ingest: album completed — %s / %s (%d tracks)',
                artist.name, album.name, len(tracks),
            )

        logger.info('ingest: artist completed — %s', artist.name)

    return result
