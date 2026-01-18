from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Iterable, Sequence

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from catalog import spotify_stub
from catalog.models import Genre

logger = logging.getLogger(__name__)
_GENRE_SOURCE = 'spotify.recommendation_genre_seeds'


@dataclass(frozen=True)
class GenreSyncResult:
    created: int
    updated: int
    total: int
    source: str = _GENRE_SOURCE
    synced_at: str | None = None


def _build_genre_identifier(name: str) -> str:
    base = slugify(name)[:24]
    if not base:
        digest = hashlib.sha1(name.encode('utf-8')).hexdigest()[:24]
        base = digest
    return f'genre:{base}'


def _load_genre_names() -> Sequence[str]:
    if getattr(settings, 'SPOTIFY_USE_STUB_DATA', False):
        return spotify_stub.genre_seeds()
    client = spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials())
    payload = client.recommendation_genre_seeds()
    return payload.get('genres', [])


def _update_metadata(instance: Genre, synced_at: str) -> list[str]:
    fields_to_update: list[str] = []
    spotify_data = dict(instance.spotify_data or {})
    spotify_data.update({'source': _GENRE_SOURCE, 'synced_at': synced_at})
    instance.spotify_data = spotify_data
    fields_to_update.append('spotify_data')

    custom_data = dict(instance.custom_data or {})
    custom_data['last_genre_sync'] = synced_at
    instance.custom_data = custom_data
    fields_to_update.append('custom_data')
    return fields_to_update


def _upsert_genre(name: str, synced_at: str) -> tuple[Genre, bool]:
    spotify_id = _build_genre_identifier(name)
    genre = Genre.objects.filter(spotify_id=spotify_id).first()
    if not genre:
        genre = Genre.objects.filter(name__iexact=name).first()
    created = False

    if genre is None:
        genre = Genre(spotify_id=spotify_id, name=name)
        created = True
    else:
        fields_to_update: list[str] = []
        if genre.spotify_id != spotify_id:
            genre.spotify_id = spotify_id
            fields_to_update.append('spotify_id')
        if genre.name != name:
            genre.name = name
            fields_to_update.append('name')
        fields_to_update.extend(_update_metadata(genre, synced_at))
        genre.save(update_fields=list(dict.fromkeys(fields_to_update)))
        return genre, created

    _update_metadata(genre, synced_at)
    genre.save()
    return genre, created


def sync_spotify_genres(names: Iterable[str] | None = None) -> GenreSyncResult:
    genre_names: Sequence[str]
    if names is None:
        genre_names = _load_genre_names()
    else:
        genre_names = list(names)

    genre_names = sorted({name.strip() for name in genre_names if name})
    synced_at = timezone.now().isoformat()
    created = updated = 0

    if not genre_names:
        logger.warning('Spotify genre sync returned no genres.')
        return GenreSyncResult(created=0, updated=0, total=0, synced_at=synced_at)

    with transaction.atomic():
        for name in genre_names:
            _, was_created = _upsert_genre(name, synced_at)
            if was_created:
                created += 1
            else:
                updated += 1

    logger.info('Synchronized %s genres (created=%s, updated=%s).', len(genre_names), created, updated)
    return GenreSyncResult(created=created, updated=updated, total=len(genre_names), synced_at=synced_at)
