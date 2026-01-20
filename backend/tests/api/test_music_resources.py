from datetime import date
from unittest import mock
from rest_framework import status
from rest_framework.test import APITestCase

from juke_auth.models import JukeUser
from tests.utils import create_genre, create_artist, create_album, create_track


class MusicResourceTests(APITestCase):
    genre_url = '/api/v1/genres/'
    artist_url = '/api/v1/artists/'
    album_url = '/api/v1/albums/'
    track_url = '/api/v1/tracks/'

    def test_get_genres_fail_not_authenticated(self):
        resp = self.client.get(self.genre_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_artists_fail_not_authenticated(self):
        resp = self.client.get(self.artist_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_albums_fail_not_authenticated(self):
        resp = self.client.get(self.album_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_tracks_fail_not_authenticated(self):
        resp = self.client.get(self.track_url, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_genres_ok(self):
        create_genre(name='genre-1')
        create_genre(name='genre-2')
        self.client.force_login(JukeUser.objects.create(username='test-user', password='test-password'))
        resp = self.client.get(self.genre_url, format='json)')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 2)

    def test_get_artists_ok(self):
        create_artist(name='artist-1')
        self.client.force_login(JukeUser.objects.create(username='test-user', password='test-password'))
        resp = self.client.get(self.artist_url, format='json)')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 1)

    def test_get_albums_ok(self):
        create_album(name='album-1', total_tracks=5, release_date=date(year=1970, month=1, day=3))
        self.client.force_login(JukeUser.objects.create(username='test-user', password='test-password'))
        resp = self.client.get(self.album_url, format='json)')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 1)

    def test_get_tracks_ok(self):
        a1 = create_album(name='album-1', total_tracks=10, release_date=date(year=1970, month=1, day=3))
        for i in range(1, 11):
            create_track(name=f"track_{i}", duration_ms=1000 + i, track_number=i, album=a1)

        self.client.force_login(JukeUser.objects.create(username='test-user', password='test-password'))
        resp = self.client.get(self.track_url, format='json)')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['count'], 10)

    @mock.patch('catalog.views.controller.route')
    def test_internal_requests_skip_external_controller(self, mock_route):
        create_artist(name='artist-1')
        self.client.force_login(JukeUser.objects.create(username='internal-user', password='pw'))

        response = self.client.get(self.artist_url, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        mock_route.assert_not_called()
