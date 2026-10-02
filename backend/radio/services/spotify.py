"""Client-credentials Spotify access for radio: hydration, top tracks, album tracks, search.

Every call degrades to an empty result on failure so the radio never 500s because Spotify
hiccuped, and never waits long:

- short request timeouts and no retries (so spotipy never sleeps on a 429 ``Retry-After``);
- a circuit breaker that skips Spotify for ``BREAKER_SECONDS`` after a transport failure,
  timeout, 5xx or 429;
- an optional per-request time budget (``budget()``) shared by every Spotify and MLCore call
  made while picking tracks.

``SPOTIFY_USE_STUB_DATA`` swaps in deterministic stub data (tests/dev).
"""
from __future__ import annotations

import contextlib
import contextvars
import hashlib
import logging
import time
from typing import Any, Dict, Iterable, List, Optional

from django.conf import settings
from django.core.cache import cache

from catalog import spotify_stub

logger = logging.getLogger(__name__)

TRACK_CACHE_TTL = 7 * 24 * 3600
LIST_CACHE_TTL = 24 * 3600
TRACK_BATCH = 50
SINGLE_LOOKUP_LIMIT = 5
SEARCH_LIMIT = 10
MARKET = 'US'
REQUEST_TIMEOUT_SECONDS = float(getattr(settings, 'RADIO_SPOTIFY_TIMEOUT_SECONDS', 2))
BREAKER_SECONDS = int(getattr(settings, 'RADIO_SPOTIFY_BREAKER_SECONDS', 60))
_CACHE_PREFIX = 'radio:spotify:v2'
_BREAKER_KEY = f'{_CACHE_PREFIX}:breaker'

_deadline: contextvars.ContextVar[Optional[float]] = contextvars.ContextVar('radio_deadline', default=None)


@contextlib.contextmanager
def budget(seconds: float):
    """Bound every Spotify/MLCore call made inside the block by one overall time budget.

    A nested budget never extends an outer one. Calls already in flight finish within their
    own request timeout, so the worst case is the budget plus one request timeout.
    """
    outer = _deadline.get()
    deadline = time.monotonic() + seconds
    token = _deadline.set(min(deadline, outer) if outer is not None else deadline)
    try:
        yield
    finally:
        _deadline.reset(token)


def remaining() -> Optional[float]:
    """Seconds left in the current budget (None when unbounded)."""
    deadline = _deadline.get()
    return None if deadline is None else max(0.0, deadline - time.monotonic())


def out_of_time(minimum: float = 0.05) -> bool:
    left = remaining()
    return left is not None and left < minimum


class StubSpotify:
    """Spotipy-shaped facade over ``catalog.spotify_stub`` for stubbed environments."""

    def track(self, track_id, market=None):
        return spotify_stub.track_detail(f'spotify:track:{track_id}')

    def tracks(self, tracks, market=None):
        return {'tracks': [self.track(track_id) for track_id in tracks]}

    def artist(self, artist_id):
        return spotify_stub.artist_detail(f'spotify:artist:{artist_id}')

    def artists(self, artists):
        return {'artists': [self.artist(artist_id) for artist_id in artists]}

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

    def search(self, q, limit=SEARCH_LIMIT, type='track', market=None, offset=0):
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
                client_credentials_manager=SpotifyClientCredentials(requests_timeout=REQUEST_TIMEOUT_SECONDS),
                requests_timeout=REQUEST_TIMEOUT_SECONDS,
                retries=0,
                status_retries=0,
                status_forcelist=(),
                backoff_factor=0,
            )
        except Exception as exc:  # misconfigured credentials must not break radio
            logger.warning('Spotify client unavailable for radio: %s', exc)
            return None
    return _client


def http_status(exc: Exception) -> Optional[int]:
    return getattr(exc, 'http_status', None)


def breaker_open() -> bool:
    return bool(cache.get(_BREAKER_KEY))


def _trip_breaker(exc: Exception) -> None:
    status = http_status(exc)
    # A 4xx other than 429 means "this request is wrong", not "Spotify is unhealthy".
    if status is not None and 400 <= status < 500 and status != 429:
        return
    cache.set(_BREAKER_KEY, True, BREAKER_SECONDS)
    logger.warning('Spotify unavailable for radio (%s); skipping Spotify for %ss', exc, BREAKER_SECONDS)


def _call(description: str, operation, *, failures: Optional[list] = None):
    if out_of_time() or breaker_open():
        return None
    client = get_client()
    if client is None:
        return None
    try:
        return operation(client)
    except Exception as exc:  # spotipy/requests raise a variety of errors
        logger.warning('Spotify %s failed: %s', description, exc)
        _trip_breaker(exc)
        if failures is not None:
            failures.append(exc)
        return None


def _artwork(images) -> Optional[str]:
    if isinstance(images, list):
        for image in images:
            if isinstance(image, dict) and image.get('url'):
                return image['url']
    return None


def track_payload(item: Dict[str, Any], *, album: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    """Normalize a Spotify track object into the radio ``Track`` contract shape.

    ``artistIds``/``artistNames`` are additive: every credited artist, so exclusions can
    match featured (non-first) artists.
    """
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
        'artistIds': [artist['id'] for artist in artists if artist.get('id')],
        'artistNames': [artist['name'] for artist in artists if artist.get('name')],
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
    """Hydrate track ids into ``Track`` payloads via ``GET /v1/tracks?ids=`` batches (cached).

    Single-track lookups are a fallback only when Spotify *refuses* the batch endpoint
    (403/404, e.g. restricted app tiers), capped at ``SINGLE_LOOKUP_LIMIT`` per call.
    Timeouts, 5xx and 429 trip the circuit breaker instead.
    """
    ids = [track_id for track_id in dict.fromkeys(track_ids) if track_id]
    result = cached_tracks(ids)
    missing = [track_id for track_id in ids if track_id not in result]
    fetched = []
    singles_left = SINGLE_LOOKUP_LIMIT
    for start in range(0, len(missing), TRACK_BATCH):
        batch = missing[start:start + TRACK_BATCH]
        failures: list = []
        payload = _call('tracks batch', lambda client, batch=batch: client.tracks(batch, market=MARKET), failures=failures)
        if payload is None and failures and http_status(failures[0]) in (403, 404):
            singles = batch[:singles_left]
            singles_left -= len(singles)
            items = [_call('track', lambda client, track_id=track_id: client.track(track_id, market=MARKET)) for track_id in singles]
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


def artist_name(artist_id: str) -> str:
    """Display name for an artist id ('' when Spotify can't tell us right now)."""
    if not artist_id:
        return ''
    key = f'{_CACHE_PREFIX}:artist-name:{artist_id}'
    cached = cache.get(key)
    if cached is not None:
        return cached
    payload = _call('artist', lambda client: client.artist(artist_id))
    name = (payload or {}).get('name') or ''
    if name:
        cache.set(key, name, TRACK_CACHE_TTL)
    return name


ARTIST_BATCH = 50


ARTISTS_REFUSED_KEY = f'{_CACHE_PREFIX}:artists-refused'
ARTISTS_REFUSED_SECONDS = 3600
ARTIST_GENRES_NEGATIVE_SECONDS = 600


def artist_genres(artist_ids: Iterable[str]) -> Dict[str, List[str]]:
    """artist id → Spotify genres via ``GET /v1/artists?ids=`` batches (cached, budget-bound).

    Failures are cheap to repeat-avoid: a 403 marks the endpoint refused for an hour, and ids
    from any failed batch are negative-cached (as "no genres") for ten minutes. Transport
    errors, 5xx and 429 also trip the shared circuit breaker in ``_call``.
    """
    ids = [artist_id for artist_id in dict.fromkeys(artist_ids) if artist_id]
    keys = {artist_id: f'{_CACHE_PREFIX}:artist-genres:{artist_id}' for artist_id in ids}
    found = cache.get_many(list(keys.values()))
    result = {artist_id: found[key] for artist_id, key in keys.items() if key in found}
    missing = [artist_id for artist_id in ids if artist_id not in result]
    if not missing or cache.get(ARTISTS_REFUSED_KEY):
        return result
    fresh: Dict[str, List[str]] = {}
    failed: List[str] = []
    for start in range(0, len(missing), ARTIST_BATCH):
        batch = missing[start:start + ARTIST_BATCH]
        failures: list = []
        payload = _call('artists batch', lambda client, batch=batch: client.artists(batch), failures=failures)
        if payload is None:
            if failures:
                failed += batch
                if http_status(failures[0]) == 403:
                    cache.set(ARTISTS_REFUSED_KEY, True, ARTISTS_REFUSED_SECONDS)
                    logger.info('Spotify refused the artists endpoint; skipping genre lookups for %ss', ARTISTS_REFUSED_SECONDS)
                    break
            continue
        for item in payload.get('artists') or []:
            if isinstance(item, dict) and item.get('id'):
                fresh[item['id']] = [genre for genre in item.get('genres') or [] if isinstance(genre, str)]
    if fresh:
        cache.set_many({keys[artist_id]: genres for artist_id, genres in fresh.items() if artist_id in keys}, TRACK_CACHE_TTL)
        result.update(fresh)
    if failed:
        cache.set_many({keys[artist_id]: [] for artist_id in failed}, ARTIST_GENRES_NEGATIVE_SECONDS)
    return result


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


def search(query: str, kind: str = 'tracks', limit: int = SEARCH_LIMIT, offset: int = 0) -> List[Dict[str, Any]]:
    """Raw Spotify search items for ``kind`` (tracks|artists|albums)."""
    spotify_type = SEARCH_TYPES[kind]
    query = (query or '').strip()
    if not query:
        return []
    digest = hashlib.sha1(query.casefold().encode()).hexdigest()
    key = f'{_CACHE_PREFIX}:search:{spotify_type}:{limit}:{offset}:{digest}'
    cached = cache.get(key)
    if cached is not None:
        return cached
    search_kwargs = {'q': query, 'limit': limit, 'type': spotify_type, 'market': MARKET}
    if offset:
        search_kwargs['offset'] = offset
    payload = _call('search', lambda client: client.search(**search_kwargs))
    items = [item for item in ((payload or {}).get(f'{spotify_type}s') or {}).get('items') or [] if isinstance(item, dict)]
    if payload is not None:
        cache.set(key, items, 3600)
    return items


def search_tracks(query: str, limit: int = SEARCH_LIMIT, offset: int = 0) -> List[Dict[str, Any]]:
    tracks = [track for track in (track_payload(item) for item in search(query, 'tracks', limit, offset)) if track]
    remember_tracks(tracks)
    return tracks
