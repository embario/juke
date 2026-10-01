"""Shared fakes for radio tests: a spotipy-shaped Spotify double and MLCore fixtures."""
import uuid

from spotipy.exceptions import SpotifyException

from mlcore.models import CanonicalItem, CanonicalItemAlias


def sp_track(track_id, artist_id='artist-a', artist_name='Artist A', album_id='album-1', name=None, image=True, featuring=()):
    return {
        'id': track_id,
        'uri': f'spotify:track:{track_id}',
        'name': name or f'Song {track_id}',
        'duration_ms': 200000,
        'artists': [{'id': artist_id, 'name': artist_name}] + [{'id': fid, 'name': fname} for fid, fname in featuring],
        'album': {'id': album_id, 'name': f'Album {album_id}',
                  'images': [{'url': f'https://img.test/{album_id}.jpg'}] if image else []},
    }


class FakeSpotify:
    def __init__(self, tracks=(), top=None, search=None, album_tracks=None, fail_batch=False, artists=None):
        self.db = {track['id']: track for track in tracks}
        self.top = top or {}
        self.search_results = search or {}
        self.albums = album_tracks or {}
        self.fail_batch = fail_batch  # True → 403 refusal, or an exception instance to raise
        self.artists = artists or {}
        self.calls = []

    def add(self, *tracks):
        for track in tracks:
            self.db[track['id']] = track

    def tracks(self, ids, market=None):
        self.calls.append(('tracks', list(ids)))
        if self.fail_batch is True:
            raise SpotifyException(403, -1, 'batch endpoint forbidden')
        if self.fail_batch:
            raise self.fail_batch
        return {'tracks': [self.db.get(track_id) for track_id in ids]}

    def track(self, track_id, market=None):
        self.calls.append(('track', track_id))
        if track_id not in self.db:
            raise SpotifyException(404, -1, 'not found')
        return self.db[track_id]

    def artist(self, artist_id):
        self.calls.append(('artist', artist_id))
        if artist_id not in self.artists:
            raise SpotifyException(404, -1, 'no such artist')
        return {'id': artist_id, 'name': self.artists[artist_id]}

    def artist_top_tracks(self, artist_id, country=None):
        self.calls.append(('top', artist_id))
        return {'tracks': self.top.get(artist_id, [])}

    def album_tracks(self, album_id, limit=50, market=None):
        self.calls.append(('album', album_id))
        return {'items': [{'id': track_id} for track_id in self.albums.get(album_id, [])]}

    def search(self, q, limit=10, type='track', market=None):
        self.calls.append(('search', q, type))
        return {f'{type}s': {'items': self.search_results.get((q, type), self.search_results.get(q, []))}}

    def called(self, kind):
        return [call for call in self.calls if call[0] == kind]


def canonical_with_alias(spotify_id, *, status='active', source='spotify', confidence=1.0, evidence=None):
    item = CanonicalItem.objects.create(id=uuid.uuid4(), item_type='spotify_track', canonical_key=f'test:{uuid.uuid4()}')
    CanonicalItemAlias.objects.create(
        canonical_item=item, source=source, resource_type='track', source_id=spotify_id, status=status, confidence=confidence,
        metadata={'evidence': evidence or {'name': f'Evidence {spotify_id}', 'artists': ['Evidence Artist'],
                                           'duration_ms': 123000, 'uri': f'spotify:track:{spotify_id}'}})
    return item


def engine_response(*canonical_items):
    return {'items': [{'canonical_item_id': str(item.id), 'score': 1.0 - idx * 0.01} for idx, item in enumerate(canonical_items)]}
