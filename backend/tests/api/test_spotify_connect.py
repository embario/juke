from unittest.mock import patch

from django.conf import settings
from django.http import HttpResponseRedirect
from django.test import override_settings
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from juke_auth.models import JukeUser


class SpotifyConnectTests(APITestCase):
    endpoint = '/api/v1/auth/connect/spotify/'

    def setUp(self):
        self.user = JukeUser.objects.create_user(
            username='spotify-link-user',
            email='spotify-link@example.com',
            password='pass1234',
        )
        self.token, _ = Token.objects.get_or_create(user=self.user)

    def test_connect_requires_authenticated_context(self):
        response = self.client.get(self.endpoint)

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn('/login?error=spotify_auth_failed', response['Location'])

    @patch('juke_auth.views.social_views.auth')
    def test_connect_with_token_query_logs_in_user_and_starts_oauth(self, mock_social_auth):
        mock_social_auth.return_value = HttpResponseRedirect('https://accounts.spotify.com/authorize')
        return_to = f"{settings.FRONTEND_URL.rstrip('/')}/"

        response = self.client.get(f"{self.endpoint}?token={self.token.key}&return_to={return_to}")

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(response['Location'], 'https://accounts.spotify.com/authorize')
        self.assertEqual(response.wsgi_request.user.id, self.user.id)
        self.assertEqual(response.wsgi_request.session.get('spotify_connect_user_id'), self.user.id)
        self.assertEqual(response.wsgi_request.session.get('spotify_connect_return_to'), return_to)

    @override_settings(SPOTIFY_CONNECT_ALLOWED_RETURN_SCHEMES=['juke', 'shotclock'])
    @patch('juke_auth.views.social_views.auth')
    def test_connect_accepts_mobile_return_scheme(self, mock_social_auth):
        mock_social_auth.return_value = HttpResponseRedirect('https://accounts.spotify.com/authorize')
        return_to = 'shotclock://spotify-callback'

        response = self.client.get(f"{self.endpoint}?token={self.token.key}&return_to={return_to}")

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(response.wsgi_request.session.get('spotify_connect_return_to'), return_to)
