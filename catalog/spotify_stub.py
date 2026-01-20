import copy
from typing import Any, Dict, List

TOOL_ARTIST_ID = "2yEwvVSSSUkcLeSTNyHKh8"
LATERALUS_ALBUM_ID = "5l5m1hnH4punS1GQXgEi3T"
DISPOSITION_TRACK_ID = "1FRlNrHd4OGNIEVgFuX9Fu"
GENRE_SEEDS = [
    'progressive metal',
    'post-rock',
    'experimental jazz',
    'dark ambient',
    'math rock',
    'trip hop',
    'psychedelic rock',
    'noise pop',
    'symphonic metal',
    'electro house',
]


def _build_artist(idx: int, spotify_id: str | None = None, name: str | None = None) -> Dict[str, Any]:
    artist_id = spotify_id or f"stub-artist-{idx}"
    return {
        'id': artist_id,
        'type': 'artist',
        'uri': f"spotify:artist:{artist_id}",
        'name': name or f"Stub Artist {idx}",
        'genres': ['progressive metal'],
        'popularity': 42 + idx,
        'followers': {'total': 1000 + idx},
        'images': [],
    }


def _build_album(
    idx: int,
    spotify_id: str | None = None,
    name: str | None = None,
    *,
    release_date: str = '2000-01-01',
    total_tracks: int = 10,
    artists: List[Dict[str, Any]] | None = None,
) -> Dict[str, Any]:
    album_id = spotify_id or f"stub-album-{idx}"
    artists = artists or [{
        'id': f"stub-artist-{idx}",
        'name': f"Stub Artist {idx}",
    }]
    return {
        'id': album_id,
        'type': 'album',
        'uri': f"spotify:album:{album_id}",
        'name': name or f"Stub Album {idx}",
        'album_type': 'album',
        'total_tracks': total_tracks,
        'release_date': release_date,
        'release_date_precision': 'day',
        'images': [],
        'artists': artists,
    }


def _build_track(
    idx: int,
    spotify_id: str | None = None,
    name: str | None = None,
    *,
    album: Dict[str, Any] | None = None,
    duration_ms: int = 200000,
    track_number: int | None = None,
    disc_number: int = 1,
    explicit: bool = False,
) -> Dict[str, Any]:
    track_id = spotify_id or f"stub-track-{idx}"
    album_payload = copy.deepcopy(album or _build_album(idx))
    return {
        'id': track_id,
        'type': 'track',
        'uri': f"spotify:track:{track_id}",
        'name': name or f"Stub Track {idx}",
        'album': album_payload,
        'duration_ms': duration_ms,
        'track_number': track_number or idx + 1,
        'disc_number': disc_number,
        'explicit': explicit,
    }


TOOL_ARTIST = _build_artist(0, spotify_id=TOOL_ARTIST_ID, name='TOOL')
LATERALUS_ALBUM = _build_album(
    0,
    spotify_id=LATERALUS_ALBUM_ID,
    name='Lateralus',
    release_date='2001-05-15',
    total_tracks=13,
    artists=[{'id': TOOL_ARTIST_ID, 'name': 'TOOL'}],
)
DISPOSITION_TRACK = _build_track(
    0,
    spotify_id=DISPOSITION_TRACK_ID,
    name='Disposition',
    album=LATERALUS_ALBUM,
    duration_ms=286266,
    track_number=10,
    disc_number=1,
    explicit=False,
)


def _parse_uri(uri: str) -> str:
    return uri.split(':')[-1]


def _generate_items(builder, resource_type: str) -> Dict[str, Any]:
    items = [builder(idx) for idx in range(10)]
    return {
        'href': f"https://stub.local/{resource_type}s",
        'items': items,
        'limit': len(items),
        'offset': 0,
        'total': len(items),
        'previous': None,
    }


def search_response(resource_type: str) -> Dict[str, Any]:
    factories = {
        'artist': lambda idx: copy.deepcopy(_build_artist(idx)),
        'album': lambda idx: copy.deepcopy(_build_album(idx)),
        'track': lambda idx: copy.deepcopy(_build_track(idx)),
    }
    if resource_type not in factories:
        raise ValueError(f"Unsupported stub resource type: {resource_type}")
    return _generate_items(factories[resource_type], resource_type)


def artist_detail(uri: str) -> Dict[str, Any]:
    spotify_id = _parse_uri(uri)
    if spotify_id == TOOL_ARTIST_ID:
        return copy.deepcopy(TOOL_ARTIST)
    return _build_artist(0, spotify_id=spotify_id, name=f"Stub Artist {spotify_id[-4:]}" if spotify_id else None)


def album_detail(uri: str) -> Dict[str, Any]:
    spotify_id = _parse_uri(uri)
    if spotify_id == LATERALUS_ALBUM_ID:
        return copy.deepcopy(LATERALUS_ALBUM)
    return _build_album(0, spotify_id=spotify_id, name=f"Stub Album {spotify_id[-4:]}" if spotify_id else None)


def track_detail(uri: str) -> Dict[str, Any]:
    spotify_id = _parse_uri(uri)
    if spotify_id == DISPOSITION_TRACK_ID:
        return copy.deepcopy(DISPOSITION_TRACK)
    return _build_track(0, spotify_id=spotify_id, name=f"Stub Track {spotify_id[-4:]}" if spotify_id else None)


def genre_seeds() -> List[str]:
    return list(GENRE_SEEDS)
