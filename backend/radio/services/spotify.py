"""Client-credentials Spotify access for radio: hydration, top tracks, album tracks, search.

Every call degrades to an empty result on failure so the radio never 500s because Spotify
hiccuped. ``SPOTIFY_USE_STUB_DATA`` swaps in deterministic stub data (tests/dev).
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Dict, Iterable, List, Optional

from django.conf import settings
from django.core.cache import cache

from catalog import spotify_stub

logger = logging.getLogger(__name__)

TRACK_CACHE_TTL = 7 * 24 * 3600
LIST_CACHE_TTL = 24 * 3600
TRACK_BATCH = 50
SEARCH_LIMIT = 10
MARKET = 'US'
_CACHE_PREFIX = 'radio:spotify:v1'


class StubSpotify:
    """Spotipy-shaped facade over ``catalog.spotify_stub`` for stubbed environments."""

    def track(self, track_id, market=None):
        return spotify_stub.track_detail(f'spotify:track:{track_id}')

    def tracks(self, tracks, market=None):
        return {'tracks': [self.track(track_id) for track_id in tracks]}

    def artist_top_tracks(self, artist_id, country=MARKET):
        album = spotify_stub.album_detail('spotify:album:stub-album-0')
        album['artists'] = [{'id': artist_id, 'name': f'Stub Artist {artist_id[-4:]}'}]
        items = []
        for idx in range(5):
            track = spotify_stub.track_detail(f'spotify:track:{artist_id[-6:]}-top-{idx}')
            track['album'] = album
            track['artists'] = album['artists']
            items.append(track)
        return {'tracks': items}

    def album_tracks(self, album_id, limit=50, market=None):
        return spotify_stub.album_tracks(album_id)

    def search(self, q, limit=SEARCH_LIMIT, type='track', market=None):
        key = f'{type}s'
        payload = spotify_stub.search_response(type)
        payload['items'] = payload['items'][:limit]
        return {key: payload}


_client = None


def get_client():
    """Return a spotipy client (client credentials) or the stub; None if unavailable."""
    global _client
    if getattr(settings, 'SPOTIFY_USE_STUB_DATA', False):
        return StubSpotify()
    if _client is None:
        try:
            import spotipy
            from spotipy.oauth2 import SpotifyClientCredentials
            _client = spotipy.Spotify(
                client_credentials_manager=SpotifyClientCredentials(),
                requests_timeout=8,
                retries=1,
            )
        except Exception as exc:  # misconfigured credentials must not break radio
            logger.warning('Spotify client unavailable for radio: %s', exc)
            return None
    return _client


def _call(description: str, operation):
    client = get_client()
    if client is None:
        return None
    try:
        return operation(client)
    except Exception as exc:  # spotipy/requests raise a variety of errors
        logger.warning('Spotify %s failed: %s', description, exc)
        return None


def _artwork(images) -> Optional[str]:
    if isinstance(images, list):
        for image in images:
            if isinstance(image, dict) and image.get('url'):
                return image['url']
    return None


def track_payload(item: Dict[str, Any], *, album: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Normalize a Spotify track object into the radio ``Track`` contract shape."""
    if not isinstance(item, dict) or not item.get('id'):
        return None
    album = album or item.get('album') or {}
    artists = [artist for artist in (item.get('artists') or album.get('artists') or []) if isinstance(artist, dict)]
    return {
        'spotifyId': item['id'],
        'uri': item.get('uri') or f"spotify:track:{item['id']}",
        'title': item.get('name') or '',
        'artist': ', '.join(artist.get('name') or '' for artist in artists if artist.get('name')),
        'artistId': (artists[0].get('id') or '') if artists else '',
        'album': album.get('name') or '',
        'albumId': album.get('id') or '',
        'artworkUrl': _artwork(album.get('images')),
        'durationMs': int(item.get('duration_ms') or 0),
    }


def _track_key(track_id: str) -> str:
    return f'{_CACHE_PREFIX}:track:{track_id}'


def cached_tracks(track_ids: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    """Cache-only lookup (no network) — for cheap decorations like station thumbnails."""
    ids = [track_id for track_id in dict.fromkeys(track_ids) if track_id]
    found = cache.get_many([_track_key(track_id) for track_id in ids])
    return {track_id: found[_track_key(track_id)] for track_id in ids if _track_key(track_id) in found}


def remember_tracks(tracks: Iterable[Dict[str, Any]]) -> None:
    cache.set_many({_track_key(track['spotifyId']): track for track in tracks if track and track.get('spotifyId')},
                   TRACK_CACHE_TTL)


def get_tracks(track_ids: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    """Hydrate track ids into ``Track`` payloads via ``GET /v1/tracks?ids=`` batches (cached)."""
    ids = [track_id for track_id in dict.fromkeys(track_ids) if track_id]
    result = cached_tracks(ids)
    missing = [track_id for track_id in ids if track_id not in result]
    fetched = []
    for start in range(0, len(missing), TRACK_BATCH):
        batch = missing[start:start + TRACK_BATCH]
        payload = _call('tracks batch', lambda client, batch=batch: client.tracks(batch, market=MARKET))
        if payload is None and len(batch) > 1:
            # Some app tiers reject the batch endpoint; fall back to single lookups.
            items = [_call('track', lambda client, track_id=track_id: client.track(track_id, market=MARKET)) for track_id in batch]
        else:
            items = (payload or {}).get('tracks') or []
        for item in items:
            track = track_payload(item) if item else None
            if track:
                fetched.append(track)
    remember_tracks(fetched)
    for track in fetched:
        result[track['spotifyId']] = track
    # Spotify may relink ids; keep only what was asked for, in request order.
    return {track_id: result[track_id] for track_id in ids if track_id in result}


def artist_top_tracks(artist_id: str) -> List[Dict[str, Any]]:
    if not artist_id:
        return []
    key = f'{_CACHE_PREFIX}:artist-top:{artist_id}'
    cached = cache.get(key)
    if cached is not None:
        return cached
    payload = _call('artist top tracks', lambda client: client.artist_top_tracks(artist_id, country=MARKET))
    tracks = [track for track in (track_payload(item) for item in (payload or {}).get('tracks') or []) if track]
    if payload is not None:
        cache.set(key, tracks, LIST_CACHE_TTL)
        remember_tracks(tracks)
    return tracks


def album_track_ids(album_id: str, limit: int = 10) -> List[str]:
    if not album_id:
        return []
    key = f'{_CACHE_PREFIX}:album-tracks:{album_id}'
    cached = cache.get(key)
    if cached is None:
        payload = _call('album tracks', lambda client: client.album_tracks(album_id, limit=50, market=MARKET))
        cached = [item['id'] for item in (payload or {}).get('items') or [] if isinstance(item, dict) and item.get('id')]
        if payload is not None:
            cache.set(key, cached, LIST_CACHE_TTL)
    return cached[:limit]


SEARCH_TYPES = {'tracks': 'track', 'artists': 'artist', 'albums': 'album'}


def search(query: str, kind: str = 'tracks', limit: int = SEARCH_LIMIT) -> List[Dict[str, Any]]:
    """Raw Spotify search items for ``kind`` (tracks|artists|albums)."""
    spotify_type = SEARCH_TYPES[kind]
    query = (query or '').strip()
    if not query:
        return []
    digest = hashlib.sha1(query.casefold().encode()).hexdigest()
    key = f'{_CACHE_PREFIX}:search:{spotify_type}:{limit}:{digest}'
    cached = cache.get(key)
    if cached is not None:
        return cached
    payload = _call('search', lambda client: client.search(q=query, limit=limit, type=spotify_type, market=MARKET))
    items = [item for item in ((payload or {}).get(f'{spotify_type}s') or {}).get('items') or [] if isinstance(item, dict)]
    if payload is not None:
        cache.set(key, items, 3600)
    return items


def search_tracks(query: str, limit: int = SEARCH_LIMIT) -> List[Dict[str, Any]]:
    tracks = [track for track in (track_payload(item) for item in search(query, 'tracks', limit)) if track]
    remember_tracks(tracks)
    return tracks
