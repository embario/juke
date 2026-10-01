"""The crate: Spotify search, or a personal crate of seeds, loved tracks and MLCore picks."""
from __future__ import annotations

from typing import Dict, List

from radio.models import Station, TrackReaction
from radio.payloads import crate_item
from radio.services import recommend, signals, spotify

CRATE_LIMIT = 30


def _artwork(images):
    return spotify._artwork(images)


def _track_item(track: Dict) -> Dict:
    return crate_item('track', track['spotifyId'], track['title'], track['artist'], track['artworkUrl'], track=track)


def search_crate(kind: str, query: str) -> List[Dict]:
    items = spotify.search(query, kind)
    if kind == 'tracks':
        tracks = [track for track in (spotify.track_payload(item) for item in items) if track]
        spotify.remember_tracks(tracks)
        return [_track_item(track) for track in tracks]
    if kind == 'artists':
        return [crate_item('artist', item['id'], item.get('name'), ', '.join((item.get('genres') or [])[:2]),
                           _artwork(item.get('images'))) for item in items if item.get('id')]
    return [crate_item('album', item['id'], item.get('name'),
                       ', '.join(artist.get('name', '') for artist in item.get('artists') or [] if isinstance(artist, dict)),
                       _artwork(item.get('images'))) for item in items if item.get('id')]


def personal_crate(user, kind: str) -> List[Dict]:
    stations = list(Station.objects.filter(user=user))
    seeds = [seed for station in stations for seed in station.seeds or []]
    reacted = list(TrackReaction.objects.filter(user=user).exclude(reactions=[])
                   .order_by('-updated_at').values_list('spotify_track_id', flat=True)[:CRATE_LIMIT])
    loved_ids = list(dict.fromkeys(reacted + signals.learned_track_ids(user, limit=CRATE_LIMIT)))
    seed_track_ids = [seed['spotifyId'] for seed in seeds if seed.get('kind') == 'track']
    track_ids = list(dict.fromkeys(seed_track_ids + loved_ids))
    tracks = list(spotify.get_tracks(track_ids[:CRATE_LIMIT]).values())
    if len(tracks) < CRATE_LIMIT and track_ids:
        known = {track['spotifyId'] for track in tracks}
        tracks += [track for track in recommend.crate_track_picks(user, track_ids, CRATE_LIMIT) if track['spotifyId'] not in known]

    items: Dict[str, Dict] = {}
    singular = kind[:-1]

    def add_seeds():
        for seed in seeds:
            if seed.get('kind') == singular:
                items.setdefault(seed['spotifyId'], crate_item(singular, seed['spotifyId'], seed.get('title'),
                                                               seed.get('subtitle'), seed.get('artworkUrl')))

    if kind != 'tracks':
        add_seeds()
    for track in tracks:
        if kind == 'tracks':
            items.setdefault(track['spotifyId'], _track_item(track))
        elif kind == 'artists' and track.get('artistId'):
            primary = (track.get('artist') or '').split(', ')[0]
            items.setdefault(track['artistId'], crate_item('artist', track['artistId'], primary, '', track.get('artworkUrl')))
        elif kind == 'albums' and track.get('albumId'):
            items.setdefault(track['albumId'], crate_item('album', track['albumId'], track.get('album'), track.get('artist'),
                                                          track.get('artworkUrl')))
    if kind == 'tracks':
        add_seeds()  # seeds Spotify couldn't hydrate still show up
    return list(items.values())[:CRATE_LIMIT]
