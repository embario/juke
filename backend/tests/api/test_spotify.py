from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase

from juke_auth.models import JukeUser

from tests.utils import create_artist, create_album, create_track


class TestSpotify(APITestCase):
    genre_url = '/api/v1/genres/'
    artist_url = '/api/v1/artists/'
    album_url = '/api/v1/albums/'
    track_url = '/api/v1/tracks/'
    fixtures = ['tests/fixtures/internal_catalog.json']

    def setUp(self):
        self.client.force_login(JukeUser.objects.create(username='test', password='test'))

    def test_search_genres_not_available(self):
        resp = self.client.get(self.genre_url, data={'q': 'test', 'external': True}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            resp.data['detail'],
            'Service cannot satisfy request because it is not available through the Streaming Platform API.'
        )

    def test_list_genres_internal_not_authenticated(self):
        self.client.logout()
        resp = self.client.get(self.genre_url, data={'q': 'test'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data['detail'], "Authentication credentials were not provided.")

    def test_list_genres_internal_ok(self):
        resp = self.client.get(self.genre_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 1)
        self.assertEqual(resp.data['results'][0]['name'], 'test-genre')

    def test_search_artists_not_authenticated(self):
        self.client.logout()
        resp = self.client.get(self.artist_url, data={'external': True}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
        self.assertEqual(resp.data['detail'], "Authentication credentials were not provided.")

    def test_search_artists_missing_search_param(self):
        resp = self.client.get(self.artist_url, data={'external': True}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Missing search parameter 'q'.", resp.data['detail'])

    def test_search_artists_external_ok(self):
        resp = self.client.get(self.artist_url, data={'q': 'test', 'external': True}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data['results']), 10)

        for artist_data in resp.data['results']:
            self.assertEqual(artist_data['spotify_data']['type'], 'artist')
            self.assertIn('uri', artist_data['spotify_data'])
            self.assertIn('popularity', artist_data['spotify_data'])
            self.assertIn('followers', artist_data['spotify_data'])
            self.assertIn('images', artist_data['spotify_data'])

    @patch("catalog.serializers.logger")
    def test_get_artist_external_existing_in_db(self, mock_logger):
        artist = create_artist(name='TOOL', spotify_id="2yEwvVSSSUkcLeSTNyHKh8")
        self.assertEqual(artist.genres.count(), 0)
        self.assertEqual(artist.spotify_data, {})

        resp = self.client.get(f"{self.artist_url}{artist.spotify_id}/", data={'external': True}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        artist.refresh_from_db()
        self.assertTrue(artist.genres.count() > 0)
        self.assertNotEqual(artist.spotify_data, {})
        mock_logger.info.assert_called_with("Artist 'TOOL' updated.")

    def test_list_artists_internal_ok(self):
        resp = self.client.get(self.artist_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 2)
        self.assertEqual(resp.data['results'][0]['name'], 'test-artist-1')
        self.assertEqual(resp.data['results'][1]['name'], 'test-artist-2')

    def test_search_albums_external_ok(self):
        resp = self.client.get(self.album_url, data={'q': 'test', 'external': True}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data['results']), 10)

        for album_data in resp.data['results']:
            self.assertEqual(album_data['spotify_data']['type'], 'album')
            self.assertIn('uri', album_data['spotify_data'])
            self.assertIn('images', album_data['spotify_data'])

    @patch("catalog.serializers.logger")
    def test_get_album_external_existing_in_db(self, mock_logger):
        album = create_album(
            name='Lateralus',
            spotify_id="5l5m1hnH4punS1GQXgEi3T",
            total_tracks=11,  # this is wrong.
            release_date="2001-05-12",  # this is also wrong.
        )
        self.assertEqual(album.artists.count(), 0)
        self.assertEqual(album.spotify_data, {})

        resp = self.client.get(f"{self.album_url}{album.spotify_id}/", data={'external': True}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        album.refresh_from_db()
        self.assertEqual(album.artists.count(), 1)
        self.assertNotEqual(album.spotify_data, {})
        self.assertEqual(resp.data['total_tracks'], 13)  # This is correct.
        self.assertEqual(resp.data['release_date'], '2001-05-15')  # This is correct.
        mock_logger.info.assert_called_with("Album 'Lateralus' updated.")

    def test_list_albums_internal_ok(self):
        resp = self.client.get(self.album_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 1)
        self.assertEqual(resp.data['results'][0]['name'], 'test-album-1')
        self.assertEqual(resp.data['results'][0]['artists'], ['http://testserver/api/v1/artists/1/'])

    def test_search_tracks_external_ok(self):
        resp = self.client.get(self.track_url, data={'q': 'test', 'external': True}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resp.data['results']), 10)

        for track_data in resp.data['results']:
            self.assertEqual(track_data['spotify_data']['type'], 'track')
            self.assertIn('uri', track_data['spotify_data'])

    def test_list_tracks_internal_ok(self):
        resp = self.client.get(self.track_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 3)

        for idx, track_data in enumerate(resp.data['results']):
            self.assertEqual(track_data['name'], f'test-track-{idx + 1}')
            self.assertEqual(track_data['album'], 'http://testserver/api/v1/albums/1/')

    @patch("catalog.serializers.logger")
    def test_get_track_external_existing_in_db(self, mock_logger):
        album = create_album(
            name='Lateralus',
            spotify_id="5l5m1hnH4punS1GQXgEi3T",
            total_tracks=11,  # this is wrong.
            release_date="2001-05-12",  # this is also wrong.
        )

        track = create_track(
            name='Disposition',
            album=album,
            spotify_id="1FRlNrHd4OGNIEVgFuX9Fu",
            track_number=1,
            disc_number=2,
            duration_ms=1000,
            explicit=True,
        )

        resp = self.client.get(f"{self.track_url}{track.spotify_id}/", data={'external': True}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        track.refresh_from_db()
        self.assertNotEqual(track.spotify_data, {})
        self.assertEqual(resp.data['track_number'], 10)
        self.assertEqual(resp.data['disc_number'], 1)
        self.assertEqual(resp.data['duration_ms'], 286266)
        self.assertEqual(resp.data['explicit'], False)

        # Ensure album got updated, too.
        self.assertEqual(track.album.total_tracks, 13)
        self.assertEqual(str(track.album.release_date), '2001-05-15')

        calls = mock_logger.info.call_args_list
        self.assertEqual(calls[0][0][0], "Album 'Lateralus' updated.")
        self.assertEqual(calls[1][0][0], "Track 'Disposition' updated.")

    # TODO: Test get() for external & internal resources
    # Also test: Create internal resource, then query for it with external=True and make sure it gets updated.
    # Do the reverse: Query for resource with external=True and then grab it internally.
