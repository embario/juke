"""camelCase response shapes for the radio API contract."""
from radio.services import signals, spotify


def exclusion_payload(exclusion):
    return {'id': str(exclusion.id), 'scope': exclusion.scope, 'kind': exclusion.kind,
            'value': exclusion.value, 'label': exclusion.label}


def _thumbnails(station, user):
    thumbnails = [seed.get('artworkUrl') for seed in station.seeds or [] if seed.get('artworkUrl')]
    if station.is_personal and len(thumbnails) < 3 and station.learning:
        # Cache-only so listing stations never waits on Spotify.
        cached = spotify.cached_tracks(signals.learned_track_ids(user, limit=10))
        thumbnails += [track['artworkUrl'] for track in cached.values() if track.get('artworkUrl')]
    return list(dict.fromkeys(thumbnails))[:3]


def station_payload(station, exclusions):
    """``exclusions``: the user's exclusions; everywhere ones apply to every station."""
    applicable = [item for item in exclusions if item.station_id is None or item.station_id == station.id]
    return {
        'id': str(station.id),
        'name': station.name,
        'kind': station.kind,
        'frequency': float(station.frequency),
        'seeds': station.seeds or [],
        'thumbnails': _thumbnails(station, station.user),
        'feelings': station.feelings or [],
        'learning': station.learning,
        'exclusions': [exclusion_payload(item) for item in applicable],
        'createdAt': station.created_at.isoformat(),
    }


def crate_item(kind, spotify_id, title, subtitle, artwork_url, track=None):
    item = {'id': f'{kind}:{spotify_id}', 'kind': kind, 'spotifyId': spotify_id, 'title': title or '',
            'subtitle': subtitle or '', 'artworkUrl': artwork_url}
    if track is not None:
        item['track'] = track
    return item
