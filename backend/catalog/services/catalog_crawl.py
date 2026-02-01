from __future__ import annotations

import logging
from dataclasses import dataclass, field

from django.conf import settings
from django.db import IntegrityError
from django.utils import timezone

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from catalog import spotify_stub, serializers
from catalog.models import Artist

logger = logging.getLogger(__name__)

# Genre seeds drive the initial artist discovery.  The crawl searches Spotify
# once per seed and deduplicates artists across seeds before drilling down.
_GENRE_SEEDS = spotify_stub.GENRE_SEEDS

# How many artists the Spotify search endpoint returns per query.
_SEARCH_LIMIT = 20


@dataclass
class CrawlResult:
    artists_created: int = 0
    albums_created: int = 0
    tracks_created: int = 0
    artists_skipped: int = 0
    albums_skipped: int = 0
    tracks_skipped: int = 0
    failed_artist_ids: list[str] = field(default_factory=list)
    failed_track_ids: list[str] = field(default_factory=list)
    crawled_at: str | None = None


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


# ---------------------------------------------------------------------------
# Spotify / stub fetch helpers
# ---------------------------------------------------------------------------

def _search_artists_by_genre(genre_seed: str) -> list[dict]:
    """Return raw artist dicts from a genre-scoped search."""
    if getattr(settings, 'SPOTIFY_USE_STUB_DATA', False):
        data = spotify_stub.search_response('artist')
        return list(data.get('items', []))[:_SEARCH_LIMIT]
    client = _get_spotify_client()
    response = client.search(q=f'genre:"{genre_seed}"', type='artist', limit=_SEARCH_LIMIT)
    return response.get('artists', {}).get('items', [])[:_SEARCH_LIMIT]


def _fetch_artist_albums(artist_id: str) -> list[dict]:
    """Return raw album dicts for a single artist."""
    if getattr(settings, 'SPOTIFY_USE_STUB_DATA', False):
        data = spotify_stub.artist_albums(artist_id)
        return list(data.get('items', []))
    client = _get_spotify_client()
    data = client.artist_albums(artist_id, album_type='album')
    return list(data.get('items', []))


def _fetch_album_tracks(album_id: str) -> list[dict]:
    """Return raw track dicts for a single album."""
    if getattr(settings, 'SPOTIFY_USE_STUB_DATA', False):
        data = spotify_stub.album_tracks(album_id)
        return list(data.get('items', []))
    client = _get_spotify_client()
    data = client.album_tracks(album_id)
    return list(data.get('items', []))


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

def crawl_catalog() -> CrawlResult:
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
    """
    result = CrawlResult()
    pre_existing_artist_ids: set[str] = set(
        Artist.objects.values_list('spotify_id', flat=True)
    )
    seen_artist_ids: set[str] = set()  # dedup across genre searches

    for genre_seed in _GENRE_SEEDS:
        logger.info('crawl: searching genre seed "%s"', genre_seed)

        try:
            artist_payloads = _search_artists_by_genre(genre_seed)
        except Exception:
            logger.exception('crawl: search failed for genre seed "%s"', genre_seed)
            continue

        for artist_payload in artist_payloads:
            artist_id = artist_payload['id']

            if artist_id in seen_artist_ids:
                result.artists_skipped += 1
                continue
            seen_artist_ids.add(artist_id)

            try:
                _crawl_artist(artist_payload, pre_existing_artist_ids, result)
            except Exception:
                logger.exception(
                    'crawl: failed crawling artist %s (%s)',
                    artist_payload.get('name', '?'), artist_id,
                )
                result.failed_artist_ids.append(artist_id)

    result.crawled_at = timezone.now().isoformat()
    logger.info(
        'crawl: finished — artists_created=%d albums_created=%d tracks_created=%d '
        'artists_skipped=%d albums_skipped=%d tracks_skipped=%d '
        'failed_artists=%d failed_tracks=%d',
        result.artists_created, result.albums_created, result.tracks_created,
        result.artists_skipped, result.albums_skipped, result.tracks_skipped,
        len(result.failed_artist_ids), len(result.failed_track_ids),
    )
    return result


def _crawl_artist(
    artist_payload: dict,
    pre_existing_artist_ids: set[str],
    result: CrawlResult,
) -> None:
    artist_id = artist_payload['id']
    artist_name = artist_payload.get('name', '?')

    # Persist the artist (serializer does get_or_create internally).
    _save_artist(artist_payload)
    if artist_id in pre_existing_artist_ids:
        logger.debug('crawl: artist "%s" already existed, still crawling albums', artist_name)
    else:
        result.artists_created += 1
        logger.info('crawl: artist created — %s', artist_name)

    # Fetch and persist albums.  Spotipy's artist_albums response includes only
    # a minimal artist stub (id + name) which may not match the name the
    # serializer already persisted.  Rewrite the artists list with the canonical
    # payload so that the AlbumSerializer's get_or_create hits the existing row.
    artist_ref = {'id': artist_payload['id'], 'name': artist_payload['name']}
    album_payloads = _fetch_artist_albums(artist_id)
    for album_payload in album_payloads:
        album_payload['artists'] = [artist_ref]
        album_id = album_payload['id']
        _crawl_album(album_payload, album_id, artist_name, result)


def _crawl_album(
    album_payload: dict,
    album_id: str,
    artist_name: str,
    result: CrawlResult,
) -> None:
    from catalog.models import Album

    album = Album.objects.filter(spotify_id=album_id).first()
    if album is not None and album.tracks.exists():
        # Album and its tracks were already persisted (either by a previous
        # crawl run or by the on-demand HTTP path after tracks were fetched).
        # Skip the entire subtree — no re-fetch, no re-save.
        result.albums_skipped += 1
        logger.debug('crawl: album "%s" already existed with tracks, skipping', album_payload.get('name', '?'))
        return

    _save_album(album_payload)
    result.albums_created += 1
    logger.info('crawl: album created — %s / %s', artist_name, album_payload.get('name', '?'))

    # Fetch and persist tracks.  album_tracks returns a nested ``album`` stub
    # whose name may not match the one we just persisted (same spotify_id,
    # different generated name).  Overwrite it with the canonical album payload
    # so that SpotifyTrackSerializer's Album.get_or_create hits the existing row.
    track_payloads = _fetch_album_tracks(album_id)
    for track_payload in track_payloads:
        track_payload['album'] = album_payload
        _crawl_track(track_payload, artist_name, album_payload.get('name', '?'), result)


def _crawl_track(
    track_payload: dict,
    artist_name: str,
    album_name: str,
    result: CrawlResult,
) -> None:
    from catalog.models import Track

    track_id = track_payload['id']

    if Track.objects.filter(spotify_id=track_id).exists():
        result.tracks_skipped += 1
        return

    try:
        _save_track(track_payload)
    except IntegrityError:
        # Spotify sometimes returns multiple tracks with the same track_number
        # on an album (live versions, reissues, disc-boundary artefacts).
        # The unique constraint (album, track_number) rejects the duplicate;
        # log it and continue rather than aborting the album.
        logger.warning(
            'crawl: skipping track %s (%s) — duplicate (album, track_number) '
            'on %s / %s',
            track_payload.get('name', '?'), track_id, artist_name, album_name,
        )
        result.failed_track_ids.append(track_id)
        return

    result.tracks_created += 1
    logger.info('crawl: track created — %s / %s / %s', artist_name, album_name, track_payload.get('name', '?'))
