"""
Full, paginated artist catalog.

Spotify has no EP, live or appearance album type, so categories are derived
without schema changes:

* ``compilations`` - album_type COMPILATION
* ``live``         - the title says it is live (any provider type except compilations)
* ``eps``          - SINGLE with 4+ tracks (Spotify files EPs as singles)
* ``singles``      - remaining SINGLE
* ``albums``       - remaining ALBUM
* ``appearances``  - releases by other artists the artist appears on (provider ``appears_on``)

The provider catalog is fetched through every page and cached on the Artist
(``custom_data``) so repeat browsing does not hit the provider again until it is stale.
"""
import logging
import re
from datetime import timedelta

import spotipy
from django.conf import settings
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from spotipy.oauth2 import SpotifyClientCredentials

from catalog import spotify_stub
from catalog.models import Album

logger = logging.getLogger(__name__)

# Display order: albums and EPs first.
KINDS = ('albums', 'eps', 'singles', 'compilations', 'live', 'appearances')
EP_MIN_TRACKS = 4
SYNC_TTL = timedelta(hours=12)
PAGE_LIMIT = 50
MAX_LIMIT = 100
OWN_GROUPS = 'album,single,compilation'

_LIVE_RE = re.compile(r'\blive\b|\bunplugged\b|\bin concert\b|\bat the\b.*\bsessions?\b', re.IGNORECASE)


def classify(album):
    """The release category of an album the artist owns."""
    album_type = (album.album_type or '').upper()
    if album_type == 'COMPILATION':
        return 'compilations'
    if _LIVE_RE.search(album.name or ''):
        return 'live'
    if album_type == 'SINGLE':
        return 'eps' if (album.total_tracks or 0) >= EP_MIN_TRACKS else 'singles'
    return 'albums'


def _client():
    if getattr(settings, 'SPOTIFY_USE_STUB_DATA', False):
        return None
    return spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials())


def fetch_provider_items(spotify_id, groups):
    """Every page of an artist's releases for the given include_groups."""
    if getattr(settings, 'SPOTIFY_USE_STUB_DATA', False):
        return spotify_stub.artist_albums(spotify_id, album_types=groups).get('items', [])
    client = _client()
    payload = client.artist_albums(spotify_id, include_groups=groups, limit=PAGE_LIMIT)
    items = list(payload.get('items', []))
    while payload.get('next'):
        payload = client.next(payload)
        items.extend(payload.get('items', []))
    return items


def _store(item, artist=None):
    spotify_id = (item.get('id') or '').strip()
    if not spotify_id:
        return None
    album, _ = Album.get_or_create_with_validated_data(
        data={
            'id': spotify_id,
            'name': item.get('name') or 'Unknown album',
            'album_type': item.get('album_type') or 'album',
            'total_tracks': item.get('total_tracks') or 0,
            'release_date': item.get('release_date') or '1970-01-01',
            'release_date_precision': item.get('release_date_precision') or 'day',
        },
    )
    album.spotify_data = {
        **(album.spotify_data or {}),
        'type': item.get('type') or 'album',
        'uri': item.get('uri') or f'spotify:album:{spotify_id}',
        'images': [e.get('url') for e in item.get('images', []) if isinstance(e, dict) and e.get('url')],
    }
    album.save(update_fields=['spotify_data'])
    if artist is not None:
        album.artists.add(artist)
    return album


def _is_fresh(artist):
    stamp = (artist.custom_data or {}).get('releases_synced_at')
    when = parse_datetime(stamp) if stamp else None
    return bool(when and timezone.now() - when < SYNC_TTL)


def sync(artist, force=False):
    """Pull the complete provider catalog for the artist. Returns False when the provider failed."""
    if not artist.spotify_id or (not force and _is_fresh(artist)):
        return True
    try:
        own = fetch_provider_items(artist.spotify_id, OWN_GROUPS)
        appears = fetch_provider_items(artist.spotify_id, 'appears_on')
    except Exception as exc:  # pylint: disable=broad-except
        logger.warning("Unable to sync releases for artist '%s': %s", artist.name, exc)
        return False
    for item in own:
        _store(item, artist)
    appearance_ids = []
    for item in appears:
        album = _store(item)
        if album is not None and not album.artists.filter(pk=artist.pk).exists():
            appearance_ids.append(album.spotify_id)
    artist.custom_data = {
        **(artist.custom_data or {}),
        'releases_synced_at': timezone.now().isoformat(),
        'appearance_ids': appearance_ids,
    }
    artist.save(update_fields=['custom_data'])
    return True


def _parse_int(raw, default, lo, hi):
    try:
        return max(lo, min(hi, int(raw)))
    except (TypeError, ValueError):
        return default


def releases(artist, kind=None, limit=None, offset=None, force=False):
    """A page of the artist's releases plus per-category counts.

    ``kind=None`` returns every owned release (not appearances).
    Raises ValueError for an unknown kind.
    """
    if kind is not None and kind not in KINDS:
        raise ValueError(kind)
    limit = _parse_int(limit, PAGE_LIMIT, 1, MAX_LIMIT)
    offset = _parse_int(offset, 0, 0, 10 ** 6)
    synced = sync(artist, force=force)

    owned = list(Album.objects.filter(artists=artist).order_by('-release_date', 'name').distinct())
    groups = {k: [] for k in KINDS}
    for album in owned:
        groups[classify(album)].append(album)
    ids = (artist.custom_data or {}).get('appearance_ids') or []
    appearances = list(Album.objects.filter(spotify_id__in=ids).order_by('-release_date', 'name'))
    groups['appearances'] = [a for a in appearances if a not in owned]

    chosen = groups[kind] if kind else owned
    page = chosen[offset:offset + limit]
    next_offset = offset + limit if offset + limit < len(chosen) else None
    return {
        'count': len(chosen),
        'next_offset': next_offset,
        'synced': synced,
        'counts': {k: len(v) for k, v in groups.items()},
        'albums': page,
    }
