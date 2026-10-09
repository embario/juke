from unittest.mock import MagicMock, patch

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from catalog.services import artist_releases
from juke_auth.models import JukeUser
from tests.utils import create_artist


def _item(idx, name=None, album_type='album', total=10, date='2020-01-01'):
    return {
        'id': f'rel{idx}',
        'name': name or f'Release {idx}',
        'album_type': album_type,
        'total_tracks': total,
        'release_date': date,
        'release_date_precision': 'day',
        'type': 'album',
        'images': [{'url': f'https://img/{idx}.jpg'}],
    }


class FakeSpotify:
    """Two pages for the artist's own releases, one for appearances. Records every call."""

    def __init__(self, pages=None, appears=None):
        self.calls = []
        self.pages = pages or []
        self.appears = appears or []

    def artist_albums(self, spotify_id, include_groups=None, limit=20, offset=0):
        self.calls.append(include_groups)
        if include_groups == 'appears_on':
            return {'items': self.appears, 'next': None}
        first, *rest = self.pages
        return {'items': first, 'next': 'more' if rest else None, '_rest': rest}

    def next(self, payload):
        rest = payload['_rest']
        first, *tail = rest
        return {'items': first, 'next': 'more' if tail else None, '_rest': tail}


@override_settings(SPOTIFY_USE_STUB_DATA=False)
class ArtistReleasesTests(APITestCase):
    def setUp(self):
        self.user = JukeUser.objects.create_user(username='rel', email='rel@example.com', password='pass1234')
        self.client.force_login(self.user)
        self.artist = create_artist(name='Prolific')

    def _get(self, **params):
        return self.client.get(f'/api/v1/artists/{self.artist.pk}/releases/', params)

    def _patched(self, fake):
        return patch.object(artist_releases, '_client', return_value=fake)

    def test_every_provider_page_is_fetched_and_classified(self):
        fake = FakeSpotify(
            pages=[
                [_item(1, 'Debut'), _item(2, 'Hit', 'single', 1), _item(3, 'Mini', 'single', 5)],
                [_item(4, 'Greatest', 'compilation', 18), _item(5, 'Debut (Live)', 'album', 12), _item(6, 'Second')],
            ],
            appears=[_item(7, 'Duet Project', date='2019-05-05')],
        )
        with self._patched(fake):
            body = self._get().json()
        self.assertEqual(body['count'], 6)
        self.assertEqual(
            body['counts'],
            {'albums': 2, 'eps': 1, 'singles': 1, 'compilations': 1, 'live': 1, 'appearances': 1},
        )
        self.assertEqual(sorted(fake.calls), ['album,single,compilation', 'appears_on'])

    def test_kind_filter_and_page_window(self):
        pages = [[_item(i, f'Album {i}', date=f'20{i:02d}-01-01') for i in range(10, 17)]]
        with self._patched(FakeSpotify(pages=pages)):
            first = self._get(kind='albums', limit=3).json()
            second = self._get(kind='albums', limit=3, offset=first['next_offset']).json()
            last = self._get(kind='albums', limit=3, offset=6).json()
        self.assertEqual([r['name'] for r in first['results']], ['Album 16', 'Album 15', 'Album 14'])
        self.assertEqual(first['next_offset'], 3)
        self.assertEqual([r['name'] for r in second['results']], ['Album 13', 'Album 12', 'Album 11'])
        self.assertEqual([r['name'] for r in last['results']], ['Album 10'])
        self.assertIsNone(last['next_offset'])

    def test_appearances_are_separate_from_the_artists_own_releases(self):
        fake = FakeSpotify(pages=[[_item(1, 'Own')]], appears=[_item(2, 'Guest Spot')])
        with self._patched(fake):
            own = self._get(kind='albums').json()
            guest = self._get(kind='appearances').json()
        self.assertEqual([r['name'] for r in own['results']], ['Own'])
        self.assertEqual([r['name'] for r in guest['results']], ['Guest Spot'])

    def test_second_request_uses_the_cache_and_refresh_bypasses_it(self):
        fake = FakeSpotify(pages=[[_item(1)]])
        with self._patched(fake):
            self._get()
            self._get(kind='albums')
            self.assertEqual(len(fake.calls), 2)
            self._get(refresh='1')
        self.assertEqual(len(fake.calls), 4)

    def test_provider_failure_still_returns_cached_catalog(self):
        with self._patched(FakeSpotify(pages=[[_item(1)]])):
            self._get()
        self.artist.refresh_from_db()
        self.artist.custom_data = {}
        self.artist.save(update_fields=['custom_data'])
        broken = MagicMock()
        broken.artist_albums.side_effect = RuntimeError('rate limited')
        with self._patched(broken):
            body = self._get().json()
        self.assertFalse(body['synced'])
        self.assertEqual(body['count'], 1)

    def test_unknown_kind_is_rejected(self):
        response = self._get(kind='bootlegs')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_requires_authentication(self):
        self.client.logout()
        self.assertIn(self._get().status_code, (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN))

    @override_settings(SPOTIFY_USE_STUB_DATA=True)
    def test_stub_mode_returns_albums_and_an_appearance(self):
        self.artist.spotify_id = 'stubart'
        self.artist.save(update_fields=['spotify_id'])
        body = self._get().json()
        self.assertEqual(body['counts']['albums'], 2)
        self.assertEqual(body['counts']['appearances'], 1)
