from datetime import date
from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase

from juke_auth.models import JukeUser
from tests.utils import create_artist, create_album, create_track


class _StubExternalResponse:
    def __init__(self, payload, instance=None):
        self._payload = payload
        self.instance = instance

    @property
    def data(self):
        return self._payload


class ExternalMusicResourceAPITests(APITestCase):
    artist_url = '/api/v1/artists/'
    track_url = '/api/v1/tracks/'

    def setUp(self):
        self.user = JukeUser.objects.create_user(
            username='listener',
            password='pw',
            email='listener@example.com',
        )
        self.client.force_login(self.user)

    @patch('catalog.views.controller.route')
    def test_list_with_external_flag_uses_controller(self, mock_route):
        payload = {
            'href': 'https://stub.local/artists',
            'results': [{'id': 'artist-123', 'name': 'Stub Artist'}],
            'limit': 1,
            'count': 1,
            'offset': 0,
            'previous': None,
        }
        mock_route.return_value = _StubExternalResponse(payload)

        response = self.client.get(self.artist_url, {'external': 'true', 'q': 'Tool'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['name'], 'Stub Artist')
        mock_route.assert_called_once()
        routed_request = mock_route.call_args[0][0]
        self.assertEqual(routed_request.GET['q'], 'Tool')

    @patch('catalog.views.controller.route')
    def test_detail_with_external_flag_returns_controller_instance(self, mock_route):
        imported = create_artist(name='Imported Artist', spotify_id='ext-artist-42')
        mock_route.return_value = _StubExternalResponse({}, instance=imported)

        response = self.client.get(f'{self.artist_url}ext-artist-42/', {'external': 'true'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], imported.name)
        mock_route.assert_called_once()

    @patch('catalog.views.controller.route')
    def test_track_list_with_external_flag_uses_controller(self, mock_route):
        payload = {
            'href': 'https://stub.local/tracks',
            'results': [{'id': 'track-123', 'name': 'Stub Track'}],
            'limit': 1,
            'count': 1,
            'offset': 0,
            'previous': None,
        }
        mock_route.return_value = _StubExternalResponse(payload)

        response = self.client.get(self.track_url, {'external': 'true', 'q': 'Disposition'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['results'][0]['id'], 'track-123')
        mock_route.assert_called_once()

    @patch('catalog.views.controller.route')
    def test_track_detail_with_external_flag_uses_controller_instance(self, mock_route):
        album = create_album(name='album-x', total_tracks=10, release_date=date(2001, 5, 15))
        imported_track = create_track(
            name='Remote Track',
            album=album,
            track_number=1,
            duration_ms=123000,
            spotify_id='ext-track-7',
        )
        mock_route.return_value = _StubExternalResponse({}, instance=imported_track)

        response = self.client.get(f'{self.track_url}ext-track-7/', {'external': 'true'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['name'], 'Remote Track')
        mock_route.assert_called_once()
