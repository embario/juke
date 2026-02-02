from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Callable

from django.conf import settings
from django.db import IntegrityError
from django.db.models import Count, F, Q
from django.utils import timezone

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from spotipy.exceptions import SpotifyException

from catalog import spotify_stub, serializers
from catalog.models import Album, Artist

logger = logging.getLogger(__name__)

# Genre seeds drive the initial artist discovery.  The crawl searches Spotify
# once per seed and deduplicates artists across seeds before drilling down.
_GENRE_SEEDS = spotify_stub.GENRE_SEEDS

# How many artists the Spotify search endpoint returns per query.
_SEARCH_LIMIT = 50
_DEFAULT_REQUEST_DELAY_SECONDS = 0.5
_DEFAULT_MAX_RETRIES = 3
_DEFAULT_RETRY_BACKOFF_SECONDS = 2.0


@dataclass
class CrawlResult:
    artists_created: int = 0
    artists_updated: int = 0
    albums_created: int = 0
    albums_updated: int = 0
    tracks_created: int = 0
    tracks_updated: int = 0
    artists_skipped: int = 0
    artists_fully_hydrated_skipped: int = 0
    albums_skipped: int = 0
    tracks_skipped: int = 0
    failed_artist_ids: list[str] = field(default_factory=list)
    failed_track_ids: list[str] = field(default_factory=list)
    crawled_at: str | None = None
    completed: bool = False
    completion_reason: str | None = None


# ---------------------------------------------------------------------------
# Spotipy client (lazy singleton)
# ---------------------------------------------------------------------------

_spotify_client: spotipy.Spotify | None = None


def _get_spotify_client() -> spotipy.Spotify:
    global _spotify_client
    if _spotify_client is None:
        _spotify_client = spotipy.Spotify(
            client_credentials_manager=SpotifyClientCredentials()
        )
    return _spotify_client


def _memo_key(memo: dict, name: str) -> str:
    prefix = memo.get('redis_prefix', 'crawl_catalog')
    return f'{prefix}:{name}'


def _memo_set_store(memo: dict) -> dict[str, set[str]]:
    return memo.setdefault('sets', {})


def _memo_hash_store(memo: dict) -> dict[str, dict[str, str]]:
    return memo.setdefault('hashes', {})


def _memo_is_member(memo: dict, name: str, value: str) -> bool:
    redis_client = memo.get('redis')
    if redis_client is not None:
        try:
            key = _memo_key(memo, name)
            return bool(redis_client.sismember(key, value))
        except Exception:
            logger.warning('crawl: redis memoization failed; falling back to in-memory')
            memo.pop('redis', None)
    key = _memo_key(memo, name)
    return value in _memo_set_store(memo).setdefault(key, set())


def _memo_add(memo: dict, name: str, value: str) -> None:
    redis_client = memo.get('redis')
    if redis_client is not None:
        try:
            key = _memo_key(memo, name)
            redis_client.sadd(key, value)
            ttl_seconds = memo.get('redis_ttl_seconds')
            if ttl_seconds:
                redis_client.expire(key, int(ttl_seconds))
            return
        except Exception:
            logger.warning('crawl: redis memoization failed; falling back to in-memory')
            memo.pop('redis', None)
    key = _memo_key(memo, name)
    _memo_set_store(memo).setdefault(key, set()).add(value)


def _memo_remove(memo: dict, name: str, value: str) -> None:
    redis_client = memo.get('redis')
    if redis_client is not None:
        try:
            redis_client.srem(_memo_key(memo, name), value)
            return
        except Exception:
            logger.warning('crawl: redis memoization failed; falling back to in-memory')
            memo.pop('redis', None)
    key = _memo_key(memo, name)
    _memo_set_store(memo).setdefault(key, set()).discard(value)


def _memo_members(memo: dict, name: str) -> set[str]:
    redis_client = memo.get('redis')
    if redis_client is not None:
        try:
            return set(redis_client.smembers(_memo_key(memo, name)))
        except Exception:
            logger.warning('crawl: redis memoization failed; falling back to in-memory')
            memo.pop('redis', None)
    key = _memo_key(memo, name)
    return set(_memo_set_store(memo).get(key, set()))


def _memo_hash_get(memo: dict, name: str, key: str) -> str | None:
    redis_client = memo.get('redis')
    if redis_client is not None:
        try:
            value = redis_client.hget(_memo_key(memo, name), key)
            return value
        except Exception:
            logger.warning('crawl: redis memoization failed; falling back to in-memory')
            memo.pop('redis', None)
    return _memo_hash_store(memo).get(name, {}).get(key)


def _memo_hash_set(memo: dict, name: str, key: str, value: str) -> None:
    redis_client = memo.get('redis')
    if redis_client is not None:
        try:
            hash_key = _memo_key(memo, name)
            redis_client.hset(hash_key, key, value)
            ttl_seconds = memo.get('redis_ttl_seconds')
            if ttl_seconds:
                redis_client.expire(hash_key, int(ttl_seconds))
            return
        except Exception:
            logger.warning('crawl: redis memoization failed; falling back to in-memory')
            memo.pop('redis', None)
    _memo_hash_store(memo).setdefault(name, {})[key] = value


def _memo_set_key(memo: dict, name: str, suffix: str) -> str:
    return _memo_key(memo, f'{name}:{suffix}')


def _memo_hash_incr(memo: dict, name: str, key: str, amount: int = 1) -> int:
    redis_client = memo.get('redis')
    if redis_client is not None:
        try:
            hash_key = _memo_key(memo, name)
            value = redis_client.hincrby(hash_key, key, amount)
            ttl_seconds = memo.get('redis_ttl_seconds')
            if ttl_seconds:
                redis_client.expire(hash_key, int(ttl_seconds))
            return int(value)
        except Exception:
            logger.warning('crawl: redis memoization failed; falling back to in-memory')
            memo.pop('redis', None)
    store = _memo_hash_store(memo).setdefault(name, {})
    value = int(store.get(key, 0)) + amount
    store[key] = str(value)
    return value


def _memo_set_add(memo: dict, name: str, suffix: str, value: str) -> None:
    redis_client = memo.get('redis')
    if redis_client is not None:
        try:
            key = _memo_set_key(memo, name, suffix)
            redis_client.sadd(key, value)
            ttl_seconds = memo.get('redis_ttl_seconds')
            if ttl_seconds:
                redis_client.expire(key, int(ttl_seconds))
            return
        except Exception:
            logger.warning('crawl: redis memoization failed; falling back to in-memory')
            memo.pop('redis', None)
    key = _memo_set_key(memo, name, suffix)
    _memo_set_store(memo).setdefault(key, set()).add(value)


def _memo_set_members(memo: dict, name: str, suffix: str) -> set[str]:
    redis_client = memo.get('redis')
    if redis_client is not None:
        try:
            return set(redis_client.smembers(_memo_set_key(memo, name, suffix)))
        except Exception:
            logger.warning('crawl: redis memoization failed; falling back to in-memory')
            memo.pop('redis', None)
    key = _memo_set_key(memo, name, suffix)
    return set(_memo_set_store(memo).get(key, set()))


def _memo_set_diff_empty(memo: dict, left_key: str, right_key: str) -> bool:
    redis_client = memo.get('redis')
    if redis_client is not None:
        try:
            diff = redis_client.sdiff(left_key, right_key)
            return len(diff) == 0
        except Exception:
            logger.warning('crawl: redis memoization failed; falling back to in-memory')
            memo.pop('redis', None)
    left = _memo_set_store(memo).get(left_key, set())
    right = _memo_set_store(memo).get(right_key, set())
    return len(left.difference(right)) == 0


def _crawl_completed(memo: dict) -> tuple[bool, str | None]:
    for genre_seed in _GENRE_SEEDS:
        if not _memo_is_member(memo, 'genre_seed_done', genre_seed):
            return False, 'seed_discovery_incomplete'
        left_key = _memo_set_key(memo, 'genre_seed_artists', genre_seed)
        right_key = _memo_key(memo, 'hydrated_artists')
        if not _memo_set_diff_empty(memo, left_key, right_key):
            return False, 'artists_not_hydrated'
    return True, 'all_genres_hydrated'


def _get_retry_after_seconds(exc: SpotifyException) -> float | None:
    headers = getattr(exc, 'headers', None) or {}
    retry_after = headers.get('Retry-After') or headers.get('retry-after')
    if retry_after is None:
        return None
    try:
        return float(retry_after)
    except (TypeError, ValueError):
        return None


class SpotifyRateLimiter:
    def __init__(
        self,
        min_interval_seconds: float,
        max_retries: int,
        retry_backoff_seconds: float,
    ) -> None:
        self.min_interval_seconds = max(0.0, min_interval_seconds)
        self.max_retries = max(0, max_retries)
        self.retry_backoff_seconds = max(0.0, retry_backoff_seconds)
        self._last_request_at = 0.0

    def call(self, func, *args, **kwargs):
        attempts = 0
        last_exc = None
        last_status = None
        while True:
            self._sleep_for_interval()
            try:
                return func(*args, **kwargs)
            except SpotifyException as exc:
                status = getattr(exc, 'http_status', None)
                retry_after = _get_retry_after_seconds(exc)
                last_exc = exc
                last_status = status
                if status == 429:
                    delay = retry_after if retry_after is not None else self._backoff_delay(attempts)
                elif status is not None and status >= 500:
                    delay = self._backoff_delay(attempts)
                else:
                    raise
            finally:
                self._last_request_at = time.monotonic()

            attempts += 1
            if attempts > self.max_retries:
                logger.error(
                    'crawl: spotify request failed after %d retries (status=%s). giving up.',
                    self.max_retries, last_status,
                )
                if last_exc is not None:
                    raise last_exc
                raise
            logger.warning(
                'crawl: spotify request throttled (status=%s). retrying in %.1fs',
                status, delay,
            )
            time.sleep(delay)

    def _sleep_for_interval(self) -> None:
        if self.min_interval_seconds <= 0:
            return
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.min_interval_seconds:
            time.sleep(self.min_interval_seconds - elapsed)

    def _backoff_delay(self, attempt: int) -> float:
        if self.retry_backoff_seconds <= 0:
            return 0.0
        return min(60.0, self.retry_backoff_seconds * (2 ** attempt))


# ---------------------------------------------------------------------------
# Spotify / stub fetch helpers
# ---------------------------------------------------------------------------

def _search_artists_by_genre(
    genre_seed: str,
    rate_limiter: SpotifyRateLimiter | None = None,
    offset: int = 0,
    limit: int = _SEARCH_LIMIT,
) -> tuple[list[dict], int | None]:
    """Return raw artist dicts from a genre-scoped search."""
    if getattr(settings, 'SPOTIFY_USE_STUB_DATA', False):
        data = spotify_stub.search_response('artist')
        items = list(data.get('items', []))[:limit]
        return items, len(items)
    client = _get_spotify_client()
    if rate_limiter is None:
        response = client.search(
            q=f'genre:"{genre_seed}"',
            type='artist',
            limit=limit,
            offset=offset,
        )
    else:
        response = rate_limiter.call(
            client.search,
            q=f'genre:"{genre_seed}"',
            type='artist',
            limit=limit,
            offset=offset,
        )
    artists = response.get('artists', {})
    items = artists.get('items', [])[:limit]
    total = artists.get('total')
    return items, total


def _fetch_artist_albums(
    artist_id: str,
    rate_limiter: SpotifyRateLimiter | None = None,
) -> tuple[list[dict], int | None]:
    """Return raw album dicts for a single artist."""
    if getattr(settings, 'SPOTIFY_USE_STUB_DATA', False):
        data = spotify_stub.artist_albums(artist_id)
        items = list(data.get('items', []))
        return items, len(items)
    client = _get_spotify_client()
    albums: list[dict] = []
    seen_album_ids: set[str] = set()
    offset = 0
    limit = 50
    total: int | None = None
    while True:
        if rate_limiter is None:
            data = client.artist_albums(artist_id, album_type='album', limit=limit, offset=offset)
        else:
            data = rate_limiter.call(
                client.artist_albums,
                artist_id,
                album_type='album',
                limit=limit,
                offset=offset,
            )
        if total is None:
            total = data.get('total')
        items = list(data.get('items', []))
        for item in items:
            album_id = item.get('id')
            if not album_id or album_id in seen_album_ids:
                continue
            seen_album_ids.add(album_id)
            albums.append(item)
        if len(items) < limit:
            break
        offset += limit
    return albums, total


def _fetch_album_tracks(
    album_id: str,
    rate_limiter: SpotifyRateLimiter | None = None,
) -> tuple[list[dict], int | None]:
    """Return raw track dicts for a single album."""
    if getattr(settings, 'SPOTIFY_USE_STUB_DATA', False):
        data = spotify_stub.album_tracks(album_id)
        items = list(data.get('items', []))
        return items, len(items)
    client = _get_spotify_client()
    tracks: list[dict] = []
    seen_track_ids: set[str] = set()
    offset = 0
    limit = 50
    total: int | None = None
    while True:
        if rate_limiter is None:
            data = client.album_tracks(album_id, limit=limit, offset=offset)
        else:
            data = rate_limiter.call(client.album_tracks, album_id, limit=limit, offset=offset)
        if total is None:
            total = data.get('total')
        items = list(data.get('items', []))
        for item in items:
            track_id = item.get('id')
            if not track_id or track_id in seen_track_ids:
                continue
            seen_track_ids.add(track_id)
            tracks.append(item)
        if len(items) < limit:
            break
        offset += limit
    return tracks, total


def _chunked(items: list[str], chunk_size: int) -> list[list[str]]:
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def _batch_fetch_albums(
    album_ids: list[str],
    rate_limiter: SpotifyRateLimiter | None = None,
) -> list[dict]:
    if getattr(settings, 'SPOTIFY_USE_STUB_DATA', False):
        return album_ids  # stub callers already have full payloads
    if not album_ids:
        return []
    client = _get_spotify_client()
    albums: list[dict] = []
    for chunk in _chunked(album_ids, 20):
        if rate_limiter is None:
            data = client.albums(chunk)
        else:
            data = rate_limiter.call(client.albums, chunk)
        albums.extend([album for album in data.get('albums', []) if album])
    return albums


def _batch_fetch_tracks(
    track_ids: list[str],
    rate_limiter: SpotifyRateLimiter | None = None,
) -> list[dict]:
    if getattr(settings, 'SPOTIFY_USE_STUB_DATA', False):
        return track_ids
    if not track_ids:
        return []
    client = _get_spotify_client()
    tracks: list[dict] = []
    for chunk in _chunked(track_ids, 50):
        if rate_limiter is None:
            data = client.tracks(chunk)
        else:
            data = rate_limiter.call(client.tracks, chunk)
        tracks.extend([track for track in data.get('tracks', []) if track])
    return tracks


# ---------------------------------------------------------------------------
# Persistence helpers (thin wrappers around existing serializers)
# ---------------------------------------------------------------------------

def _save_artist(artist_data: dict) -> None:
    ser = serializers.SpotifyArtistSerializer(data=artist_data, context={})
    ser.is_valid(raise_exception=True)
    ser.save()


def _save_album(album_data: dict) -> None:
    ser = serializers.SpotifyAlbumSerializer(data=album_data, context={})
    ser.is_valid(raise_exception=True)
    ser.save()


def _save_track(track_data: dict) -> None:
    ser = serializers.SpotifyTrackSerializer(data=track_data, context={})
    ser.is_valid(raise_exception=True)
    ser.save()


# ---------------------------------------------------------------------------
# Main crawl
# ---------------------------------------------------------------------------

def crawl_catalog(
    request_delay_seconds: float = _DEFAULT_REQUEST_DELAY_SECONDS,
    max_retries: int = _DEFAULT_MAX_RETRIES,
    retry_backoff_seconds: float = _DEFAULT_RETRY_BACKOFF_SECONDS,
    memo: dict | None = None,
    progress: Callable[..., None] | None = None,
) -> CrawlResult:
    """Discover and persist artists, albums, and tracks from Spotify.

    Strategy
    --------
    1. Search by each genre seed → collect artist payloads.
    2. Deduplicate artists by spotify_id across all genre results.
    3. For each unique artist: persist, then fetch & persist their albums, then
       for each album fetch & persist its tracks.
    4. Artists whose spotify_id already existed in the DB before the crawl are
       still fully crawled (their albums/tracks may be missing).  Use the
       ``artists_skipped`` counter only for artists that were *duplicates within
       this crawl run* (i.e. appeared in multiple genre searches).

    Errors are caught per-artist so a single Spotify failure does not abort the
    entire crawl.

    Rate limiting
    -------------
    ``request_delay_seconds`` throttles Spotify requests (default 0.2 seconds).
    ``max_retries`` controls how many times a throttled/5xx request is retried
    (default 5), and ``retry_backoff_seconds`` sets the base exponential
    backoff (default 1.0 seconds). When Spotify returns a 429 with
    ``Retry-After``, that value is honored.
    """
    result = CrawlResult()
    memo = memo or {}
    rate_limiter: SpotifyRateLimiter | None = None
    if not getattr(settings, 'SPOTIFY_USE_STUB_DATA', False):
        rate_limiter = SpotifyRateLimiter(
            min_interval_seconds=request_delay_seconds,
            max_retries=max_retries,
            retry_backoff_seconds=retry_backoff_seconds,
        )
    if _memo_hash_get(memo, 'meta', 'seeded_from_db') != '1':
        hydrated_album_ids = set(
            Album.objects.annotate(track_count=Count('tracks', distinct=True))
            .filter(track_count__gte=F('total_tracks'))
            .values_list('spotify_id', flat=True)
        )
        hydrated_artist_ids = set(
            Artist.objects.annotate(
                album_count=Count('albums', distinct=True),
                hydrated_album_count=Count(
                    'albums',
                    filter=Q(albums__spotify_id__in=hydrated_album_ids),
                    distinct=True,
                ),
            )
            .filter(album_count__gt=0, hydrated_album_count=F('album_count'))
            .values_list('spotify_id', flat=True)
        )
        for album_id in hydrated_album_ids:
            _memo_add(memo, 'hydrated_albums', album_id)
        for artist_id in hydrated_artist_ids:
            _memo_add(memo, 'hydrated_artists', artist_id)
        _memo_hash_set(memo, 'meta', 'seeded_from_db', '1')
    pre_existing_artist_ids: set[str] = set(
        Artist.objects.values_list('spotify_id', flat=True)
    )
    run_created_artist_ids: set[str] = set()
    seen_artist_ids: set[str] = set()  # dedup across genre searches

    def _emit(event: str, **data) -> None:
        if progress is not None:
            progress(event, **data)

    total_genre_seeds = len(_GENRE_SEEDS)
    for seed_index, genre_seed in enumerate(_GENRE_SEEDS, start=1):
        if _memo_is_member(memo, 'genre_seed_done', genre_seed):
            logger.debug(
                'crawl: genre seed %d/%d "%s" already queried; skipping',
                seed_index,
                total_genre_seeds,
                genre_seed,
            )
            continue
        offset = int(_memo_hash_get(memo, 'genre_seed_offsets', genre_seed) or 0)
        _emit('genre_start', genre=genre_seed, index=seed_index, total=total_genre_seeds, offset=offset)
        logger.debug('crawl: searching genre seed %d/%d "%s"', seed_index, total_genre_seeds, genre_seed)
        seed_fully_hydrated = True
        while True:
            try:
                artist_payloads, total_artists = _search_artists_by_genre(
                    genre_seed,
                    rate_limiter=rate_limiter,
                    offset=offset,
                    limit=_SEARCH_LIMIT,
                )
            except Exception:
                logger.exception('crawl: search failed for genre seed "%s"', genre_seed)
                seed_fully_hydrated = False
                break

            if not artist_payloads:
                _memo_add(memo, 'genre_seed_done', genre_seed)
                break

            if total_artists is not None:
                _emit(
                    'genre_total',
                    genre=genre_seed,
                    total_artists=total_artists,
                    offset=offset,
                )

            logger.debug(
                'crawl: genre seed %d/%d "%s" returned %d artists (offset=%d)',
                seed_index,
                total_genre_seeds,
                genre_seed,
                len(artist_payloads),
                offset,
            )

            total_artists_in_seed = len(artist_payloads)
            hydrated_artists_in_seed = 0
            for artist_position, artist_payload in enumerate(artist_payloads, start=1):
                artist_index = 1 + len(seen_artist_ids)
                artist_id = artist_payload['id']
                artist_name = artist_payload.get('name', '?')
                _emit('artist_start', artist=artist_name, artist_id=artist_id)
                logger.debug(
                    'crawl: artist %d (seed %d/%d, %d/%d): %s (%s)',
                    artist_index,
                    seed_index,
                    total_genre_seeds,
                    artist_position,
                    total_artists_in_seed,
                    artist_name,
                    artist_id,
                )

                _memo_set_add(memo, 'genre_seed_artists', genre_seed, artist_id)

                if artist_id in seen_artist_ids:
                    result.artists_skipped += 1
                    _emit('artist_result', status='skipped')
                    if not _memo_is_member(memo, 'hydrated_artists', artist_id):
                        seed_fully_hydrated = False
                    continue
                seen_artist_ids.add(artist_id)

                if _memo_is_member(memo, 'hydrated_artists', artist_id):
                    result.artists_fully_hydrated_skipped += 1
                    hydrated_artists_in_seed += 1
                    _emit('artist_result', status='skipped')
                    continue

                max_retries = int(memo.get('max_artist_retries', 5))
                retries = int(_memo_hash_get(memo, 'partial_artist_retries', artist_id) or 0)
                if retries >= max_retries:
                    _memo_add(memo, 'failed_artists', artist_id)
                    seed_fully_hydrated = False
                    _emit('artist_result', status='failed')
                    continue

                try:
                    artist_hydrated = _crawl_artist(
                        artist_payload,
                        pre_existing_artist_ids,
                        run_created_artist_ids,
                        result,
                        memo=memo,
                        rate_limiter=rate_limiter,
                        progress=progress,
                    )
                except Exception:
                    logger.exception(
                        'crawl: failed crawling artist %s (%s)',
                        artist_payload.get('name', '?'), artist_id,
                    )
                    result.failed_artist_ids.append(artist_id)
                    _memo_add(memo, 'failed_artists', artist_id)
                    _memo_hash_incr(memo, 'partial_artist_retries', artist_id, 1)
                    artist_hydrated = False

                if artist_hydrated:
                    _memo_add(memo, 'hydrated_artists', artist_id)
                    _memo_remove(memo, 'partial_artists', artist_id)
                    _memo_remove(memo, 'failed_artists', artist_id)
                    hydrated_artists_in_seed += 1
                    _emit('artist_result', status='created' if artist_id not in pre_existing_artist_ids else 'updated')
                else:
                    _memo_add(memo, 'partial_artists', artist_id)
                    _memo_hash_incr(memo, 'partial_artist_retries', artist_id, 1)
                    seed_fully_hydrated = False
                    _emit('artist_result', status='failed')

            if len(artist_payloads) < _SEARCH_LIMIT:
                _memo_add(memo, 'genre_seed_done', genre_seed)
                break

            offset += _SEARCH_LIMIT
            _memo_hash_set(memo, 'genre_seed_offsets', genre_seed, str(offset))

        if _memo_is_member(memo, 'genre_seed_done', genre_seed) and seed_fully_hydrated:
            _memo_add(memo, 'hydrated_genre_seeds', genre_seed)
        _emit('genre_done', genre=genre_seed, hydrated=seed_fully_hydrated)

    partial_artist_ids = _memo_members(memo, 'partial_artists')
    for artist_id in partial_artist_ids:
        if _memo_is_member(memo, 'hydrated_artists', artist_id):
            _memo_remove(memo, 'partial_artists', artist_id)
            continue
        max_retries = int(memo.get('max_artist_retries', 5))
        retries = int(_memo_hash_get(memo, 'partial_artist_retries', artist_id) or 0)
        if retries >= max_retries:
            _memo_add(memo, 'failed_artists', artist_id)
            continue
        artist_payload = None
        try:
            if getattr(settings, 'SPOTIFY_USE_STUB_DATA', False):
                artist_payload = spotify_stub.search_response('artist').get('items', [None])[0]
            else:
                client = _get_spotify_client()
                if rate_limiter is None:
                    artist_payload = client.artist(artist_id)
                else:
                    artist_payload = rate_limiter.call(client.artist, artist_id)
        except Exception:
            logger.exception('crawl: failed to refetch artist %s', artist_id)
            _memo_hash_incr(memo, 'partial_artist_retries', artist_id, 1)
            continue
        if artist_payload is None:
            continue
        try:
            artist_hydrated = _crawl_artist(
                artist_payload,
                pre_existing_artist_ids,
                run_created_artist_ids,
                result,
                memo=memo,
                rate_limiter=rate_limiter,
                progress=progress,
            )
        except Exception:
            logger.exception('crawl: failed crawling artist %s (%s)', artist_payload.get('name', '?'), artist_id)
            _memo_hash_incr(memo, 'partial_artist_retries', artist_id, 1)
            continue
        if artist_hydrated:
            _memo_add(memo, 'hydrated_artists', artist_id)
            _memo_remove(memo, 'partial_artists', artist_id)
            _memo_remove(memo, 'failed_artists', artist_id)
    result.crawled_at = timezone.now().isoformat()
    result.completed, result.completion_reason = _crawl_completed(memo)
    logger.info(
        'crawl: finished — artists_created=%d artists_updated=%d '
        'albums_created=%d albums_updated=%d tracks_created=%d tracks_updated=%d '
        'artists_skipped=%d artists_fully_hydrated_skipped=%d '
        'albums_skipped=%d tracks_skipped=%d '
        'failed_artists=%d failed_tracks=%d',
        result.artists_created, result.artists_updated,
        result.albums_created, result.albums_updated,
        result.tracks_created, result.tracks_updated,
        result.artists_skipped, result.artists_fully_hydrated_skipped,
        result.albums_skipped, result.tracks_skipped,
        len(result.failed_artist_ids), len(result.failed_track_ids),
    )
    return result


def _crawl_artist(
    artist_payload: dict,
    pre_existing_artist_ids: set[str],
    run_created_artist_ids: set[str],
    result: CrawlResult,
    memo: dict,
    rate_limiter: SpotifyRateLimiter | None = None,
    progress: Callable[..., None] | None = None,
) -> bool:
    artist_id = artist_payload['id']
    artist_name = artist_payload.get('name', '?')

    # Persist the artist (serializer does get_or_create internally).
    _save_artist(artist_payload)
    if artist_id in pre_existing_artist_ids:
        result.artists_updated += 1
        logger.debug('crawl: artist "%s" already existed, still crawling albums', artist_name)
    elif artist_id not in run_created_artist_ids:
        result.artists_created += 1
        run_created_artist_ids.add(artist_id)
        logger.info('crawl: artist created — %s', artist_name)

    # Fetch and persist albums.  Spotipy's artist_albums response includes only
    # a minimal artist stub (id + name) which may not match the name the
    # serializer already persisted.  Rewrite the artists list with the canonical
    # payload so that the AlbumSerializer's get_or_create hits the existing row.
    artist_ref = {'id': artist_payload['id'], 'name': artist_payload['name']}
    album_payloads, total_albums = _fetch_artist_albums(artist_id, rate_limiter=rate_limiter)
    if progress is not None and total_albums is not None:
        progress('artist_album_total', total_albums=total_albums, artist=artist_name)
    album_ids = [payload['id'] for payload in album_payloads]
    if not getattr(settings, 'SPOTIFY_USE_STUB_DATA', False):
        album_payloads = _batch_fetch_albums(album_ids, rate_limiter=rate_limiter)
    if not album_payloads:
        return False

    all_albums_hydrated = True
    for album_payload in album_payloads:
        album_payload['artists'] = [artist_ref]
        album_id = album_payload['id']
        if progress is not None:
            progress('album_start', album=album_payload.get('name', '?'), artist=artist_name)
        album_hydrated = _crawl_album(
            album_payload,
            album_id,
            artist_name,
            result,
            memo=memo,
            rate_limiter=rate_limiter,
            progress=progress,
        )
        if not album_hydrated:
            all_albums_hydrated = False

    if all_albums_hydrated:
        _memo_add(memo, 'hydrated_artists', artist_id)
        _memo_remove(memo, 'partial_artists', artist_id)
    else:
        _memo_add(memo, 'partial_artists', artist_id)
    return all_albums_hydrated


def _crawl_album(
    album_payload: dict,
    album_id: str,
    artist_name: str,
    result: CrawlResult,
    memo: dict,
    rate_limiter: SpotifyRateLimiter | None = None,
    progress: Callable[..., None] | None = None,
) -> bool:
    from catalog.models import Album

    if _memo_is_member(memo, 'hydrated_albums', album_id):
        result.albums_skipped += 1
        if progress is not None:
            progress('album_result', status='skipped')
        return True

    album = Album.objects.filter(spotify_id=album_id).first()
    if album is not None:
        result.albums_updated += 1
        if progress is not None:
            progress('album_result', status='updated')
        track_count = album.tracks.count()
        if track_count >= album.total_tracks:
            # Album and its tracks were already persisted (either by a previous
            # crawl run or by the on-demand HTTP path after tracks were fetched).
            # Skip the entire subtree — no re-fetch, no re-save.
            result.albums_skipped += 1
            logger.debug(
                'crawl: album "%s" already fully hydrated (%d/%d tracks), skipping',
                album_payload.get('name', '?'),
                track_count,
                album.total_tracks,
            )
            _memo_add(memo, 'hydrated_albums', album_id)
            if progress is not None:
                progress('album_result', status='skipped')
            return True

    _save_album(album_payload)
    result.albums_created += 1
    logger.info('crawl: album created — %s / %s', artist_name, album_payload.get('name', '?'))
    if progress is not None:
        progress('album_result', status='created')

    # Fetch and persist tracks.  album_tracks returns a nested ``album`` stub
    # whose name may not match the one we just persisted (same spotify_id,
    # different generated name).  Overwrite it with the canonical album payload
    # so that SpotifyTrackSerializer's Album.get_or_create hits the existing row.
    track_payloads, total_tracks = _fetch_album_tracks(album_id, rate_limiter=rate_limiter)
    if progress is not None and total_tracks is not None:
        progress('album_track_total', total_tracks=total_tracks, album=album_payload.get('name', '?'))
    track_ids = [payload['id'] for payload in track_payloads if payload and payload.get('id')]
    if not getattr(settings, 'SPOTIFY_USE_STUB_DATA', False):
        track_payloads = _batch_fetch_tracks(track_ids, rate_limiter=rate_limiter)
    track_payloads = [payload for payload in track_payloads if payload]
    unique_track_numbers = {payload.get('track_number') for payload in track_payloads}
    unique_track_numbers.discard(None)
    for track_payload in track_payloads:
        track_payload['album'] = album_payload
        _crawl_track(
            track_payload,
            artist_name,
            album_payload.get('name', '?'),
            result,
            progress=progress,
        )

    album = Album.objects.filter(spotify_id=album_id).first()
    if album is None:
        return False
    track_count = album.tracks.count()
    expected_unique = len(unique_track_numbers)
    if expected_unique and track_count >= expected_unique:
        _memo_add(memo, 'hydrated_albums', album_id)
        return True
    return False


def _crawl_track(
    track_payload: dict,
    artist_name: str,
    album_name: str,
    result: CrawlResult,
    progress: Callable[..., None] | None = None,
) -> None:
    from catalog.models import Track

    track_id = track_payload['id']

    if Track.objects.filter(spotify_id=track_id).exists():
        result.tracks_skipped += 1
        result.tracks_updated += 1
        if progress is not None:
            progress('track_result', status='updated')
        return

    try:
        _save_track(track_payload)
    except IntegrityError:
        # Spotify sometimes returns multiple tracks with the same track_number
        # on an album (live versions, reissues, disc-boundary artefacts).
        # The unique constraint (album, track_number) rejects the duplicate;
        # log it and continue rather than aborting the album.
        logger.debug(
            'crawl: skipping track %s (%s) — duplicate (album, track_number) '
            'on %s / %s',
            track_payload.get('name', '?'), track_id, artist_name, album_name,
        )
        result.failed_track_ids.append(track_id)
        if progress is not None:
            progress('track_result', status='failed')
        return

    result.tracks_created += 1
    logger.info('crawl: track created — %s / %s / %s', artist_name, album_name, track_payload.get('name', '?'))
    if progress is not None:
        progress('track_result', status='created')
