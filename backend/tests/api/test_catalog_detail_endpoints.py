from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase

from juke_auth.models import JukeUser
from tests.utils import create_album, create_artist, create_genre, create_track


class CatalogDetailEndpointTests(APITestCase):
    def setUp(self):
        self.user = JukeUser.objects.create_user(
            username='catalog-user',
            email='catalog@example.com',
            password='pass1234',
        )
        self.client.force_login(self.user)

        self.genre = create_genre(name='jazz')
        self.artist = create_artist(name='Miles Davis', spotify_data={'popularity': 95})
        self.related_artist = create_artist(name='John Coltrane', spotify_data={'popularity': 90})
        self.artist.genres.add(self.genre)
        self.related_artist.genres.add(self.genre)

        self.album = create_album(name='Kind of Blue', total_tracks=2, release_date=date(1959, 8, 17))
        self.related_album = create_album(name='Sketches of Spain', total_tracks=1, release_date=date(1960, 7, 18))
        self.album.artists.add(self.artist)
        self.related_album.artists.add(self.artist)

        create_track(
            name='So What',
            album=self.album,
            track_number=1,
            disc_number=1,
            duration_ms=560000,
            explicit=False,
            spotify_id='track-so-what',
        )
        create_track(
            name='Freddie Freeloader',
            album=self.album,
            track_number=2,
            disc_number=1,
            duration_ms=590000,
            explicit=False,
            spotify_id='track-freddie',
        )

    def test_genre_detail_returns_description_and_top_artists(self):
        response = self.client.get(f'/api/v1/genres/{self.genre.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('description'))
        self.assertIn('top_artists', response.data)
        self.assertEqual(response.data['top_artists'][0]['name'], 'Miles Davis')

    def test_artist_detail_returns_bio_discography_related_artists_and_top_tracks(self):
        response = self.client.get(f'/api/v1/artists/{self.artist.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('bio'))
        self.assertEqual(response.data['albums'][0]['name'], 'Sketches of Spain')
        self.assertEqual(response.data['related_artists'][0]['name'], 'John Coltrane')
        self.assertEqual(len(response.data['top_tracks']), 2)

    def test_album_detail_returns_description_tracks_and_related_albums(self):
        response = self.client.get(f'/api/v1/albums/{self.album.id}/')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('description'))
        self.assertEqual([track['track_number'] for track in response.data['tracks']], [1, 2])
        self.assertEqual(response.data['related_albums'][0]['name'], 'Sketches of Spain')

    @patch('catalog.views.controller.route')
    def test_genre_detail_with_external_param_uses_external_controller(self, mock_route):
        mock_route.return_value = SimpleNamespace(instance=self.genre)

        response = self.client.get(f'/api/v1/genres/{self.genre.id}/?external=true')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data.get('description'))
        mock_route.assert_called_once()
