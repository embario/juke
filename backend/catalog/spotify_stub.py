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


def artist_albums(artist_id: str, album_types: str = 'album') -> Dict[str, Any]:
    """Stub for spotipy.Spotify.artist_albums().

    Returns 2 deterministic albums for the given artist, each with the artist
    wired into the ``artists`` list so that the serializer can link them.
    """
    artist_stub = {'id': artist_id, 'name': f"Stub Artist {artist_id[-4:]}"}
    items = [
        _build_album(
            i,
            spotify_id=f"{artist_id}-album-{i}",
            name=f"Stub Album {artist_id[-4:]}-{i}",
            release_date=f"200{i}-06-15",
            total_tracks=3,
            artists=[artist_stub],
        )
        for i in range(2)
    ]
    return {
        'href': f"https://stub.local/artists/{artist_id}/albums",
        'items': items,
        'limit': len(items),
        'offset': 0,
        'total': len(items),
        'previous': None,
        'next': None,
    }


def album_tracks(album_id: str) -> Dict[str, Any]:
    """Stub for spotipy.Spotify.album_tracks().

    Returns 3 deterministic tracks for the given album.  The nested ``album``
    payload uses the same album_id so that SpotifyTrackSerializer can
    get-or-create the Album FK correctly.
    """
    album_stub = _build_album(0, spotify_id=album_id, name=f"Stub Album {album_id[-4:]}", total_tracks=3)
    items = [
        _build_track(
            i,
            spotify_id=f"{album_id}-track-{i}",
            name=f"Stub Track {album_id[-4:]}-{i}",
            album=album_stub,
            track_number=i + 1,
            duration_ms=180000 + i * 10000,
        )
        for i in range(3)
    ]
    return {
        'href': f"https://stub.local/albums/{album_id}/tracks",
        'items': items,
        'limit': len(items),
        'offset': 0,
        'total': len(items),
        'previous': None,
        'next': None,
    }


def genre_seeds() -> List[str]:
    return list(GENRE_SEEDS)


def _deterministic_float(spotify_id: str, seed: int, lo: float = 0.0, hi: float = 1.0) -> float:
    """Produce a stable float in [lo, hi) from a spotify_id and an integer seed."""
    import hashlib
    digest = hashlib.sha256(f"{spotify_id}:{seed}".encode()).hexdigest()
    # Take 8 hex chars → 32-bit int → normalise to [0, 1)
    raw = int(digest[:8], 16) / 0xFFFFFFFF
    return round(lo + raw * (hi - lo), 4)


def audio_features(track_ids: List[str]) -> List[Dict[str, Any]]:
    """Return stub audio-feature payloads matching Spotify's audio_features response shape.

    Each track gets deterministic values derived from its spotify_id so that the
    same ID always produces the same features across test runs.
    """
    results: List[Dict[str, Any]] = []
    for tid in track_ids:
        results.append({
            'id': tid,
            'type': 'track',
            'uri': f"spotify:track:{tid}",
            'energy': _deterministic_float(tid, 0),
            'valence': _deterministic_float(tid, 1),
            'tempo': _deterministic_float(tid, 2, 60.0, 200.0),
            'key': int(_deterministic_float(tid, 3, 0, 12)),
            'mode': 'minor' if _deterministic_float(tid, 4) < 0.5 else 'major',
            'danceability': _deterministic_float(tid, 5),
            'acousticness': _deterministic_float(tid, 6),
            'instrumentalness': _deterministic_float(tid, 7),
            'liveness': _deterministic_float(tid, 8),
            'speechiness': _deterministic_float(tid, 9),
            'loudness': _deterministic_float(tid, 10, -60.0, 0.0),
            'time_signature': int(_deterministic_float(tid, 11, 2, 7)),
        })
    return results
