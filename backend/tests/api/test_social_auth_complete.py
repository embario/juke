from unittest.mock import patch

from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from social_core.exceptions import AuthConnectionError


class SocialAuthCompleteTests(APITestCase):
    complete_url = '/api/v1/social-auth/complete/spotify/'

    @override_settings(FRONTEND_URL='http://frontend.local')
    @patch('social_django.views.complete')
    def test_spotify_complete_connection_error_redirect(self, mock_complete):
        mock_complete.side_effect = AuthConnectionError(None, 'Spotify unavailable')

        resp = self.client.get(self.complete_url)

        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertEqual(
            resp['Location'],
            'http://frontend.local/login?error=spotify_unavailable',
        )

    @patch('social_django.views.complete')
    def test_spotify_complete_connection_error_json(self, mock_complete):
        mock_complete.side_effect = AuthConnectionError(None, 'Spotify unavailable')

        resp = self.client.get(self.complete_url, HTTP_ACCEPT='application/json')

        self.assertEqual(resp.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(resp.json()['error'], 'spotify_unavailable')

    @override_settings(FRONTEND_URL='http://frontend.local')
    @patch('social_django.views.complete')
    def test_spotify_complete_generic_error_redirect(self, mock_complete):
        mock_complete.side_effect = RuntimeError('boom')

        resp = self.client.get(self.complete_url)

        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertEqual(
            resp['Location'],
            'http://frontend.local/login?error=spotify_auth_failed',
        )
