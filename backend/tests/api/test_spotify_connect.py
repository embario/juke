from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from django.conf import settings
from django.http import HttpResponseRedirect
from django.test import override_settings
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from juke_auth.models import JukeUser
from juke_auth.models import SpotifyConnectTicket


class SpotifyConnectTests(APITestCase):
    endpoint = '/api/v1/auth/connect/spotify/'
    login_endpoint = '/api/v1/social-auth/login/spotify/'

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

    @patch('juke_auth.views.do_auth')
    def test_connect_with_token_query_logs_in_user_and_starts_oauth(self, mock_do_auth):
        mock_do_auth.return_value = HttpResponseRedirect('https://accounts.spotify.com/authorize')
        return_to = f"{settings.FRONTEND_URL.rstrip('/')}/"

        response = self.client.get(f"{self.endpoint}?token={self.token.key}&return_to={return_to}")

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(response['Location'], 'https://accounts.spotify.com/authorize')
        self.assertEqual(response.wsgi_request.user.id, self.user.id)
        self.assertEqual(response.wsgi_request.session.get('spotify_connect_user_id'), self.user.id)
        self.assertEqual(response.wsgi_request.session.get('spotify_connect_return_to'), return_to)

    @patch('juke_auth.views.do_auth')
    def test_legacy_token_overrides_a_different_browser_session(self, mock_do_auth):
        browser_user = JukeUser.objects.create_user(
            username='browser-user',
            email='browser@example.com',
            password='pass1234',
        )
        self.client.force_login(browser_user)
        mock_do_auth.return_value = HttpResponseRedirect('https://accounts.spotify.com/authorize')

        response = self.client.get(f'{self.endpoint}?token={self.token.key}')

        self.assertEqual(response.wsgi_request.user.id, self.user.id)
        self.assertEqual(response.wsgi_request.session['spotify_connect_user_id'], self.user.id)

    @patch('juke_auth.views.do_auth')
    def test_single_use_ticket_selects_app_user_and_cannot_be_replayed(self, mock_do_auth):
        mock_do_auth.return_value = HttpResponseRedirect('https://accounts.spotify.com/authorize')
        return_to = f"{settings.FRONTEND_URL.rstrip('/')}/"
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')
        issued = self.client.post(
            '/api/v1/auth/spotify/connect-ticket/',
            {'return_to': return_to},
            format='json',
        )
        self.assertEqual(issued.status_code, status.HTTP_201_CREATED)
        connect_url = issued.json()['connect_url']
        self.assertNotIn(self.token.key, connect_url)
        ticket_secret = parse_qs(urlsplit(connect_url).query)['ticket'][0]

        browser_user = JukeUser.objects.create_user(
            username='ticket-browser-user',
            email='ticket-browser@example.com',
            password='pass1234',
        )
        self.client.credentials()
        self.client.force_login(browser_user)
        first = self.client.get(f'{self.endpoint}?ticket={ticket_secret}')

        self.assertEqual(first.status_code, status.HTTP_302_FOUND)
        self.assertEqual(first.wsgi_request.user.id, self.user.id)
        self.assertEqual(first.wsgi_request.session['spotify_connect_user_id'], self.user.id)
        self.assertEqual(first.wsgi_request.session['spotify_connect_return_to'], return_to)
        self.assertIsNotNone(SpotifyConnectTicket.objects.get().consumed_at)

        replay = self.client.get(f'{self.endpoint}?ticket={ticket_secret}')
        self.assertEqual(replay.status_code, status.HTTP_302_FOUND)
        self.assertIn('error=spotify_connect_ticket_invalid', replay['Location'])
        self.assertEqual(mock_do_auth.call_count, 1)

    @override_settings(SPOTIFY_CONNECT_ALLOWED_RETURN_SCHEMES=['juke', 'shotclock'])
    @patch('juke_auth.views.do_auth')
    def test_connect_accepts_mobile_return_scheme(self, mock_do_auth):
        mock_do_auth.return_value = HttpResponseRedirect('https://accounts.spotify.com/authorize')
        return_to = 'shotclock://spotify-callback'

        response = self.client.get(f"{self.endpoint}?token={self.token.key}&return_to={return_to}")

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertEqual(response.wsgi_request.session.get('spotify_connect_return_to'), return_to)

    @override_settings(
        PUBLIC_BACKEND_URL='http://auth.local:8000',
        FRONTEND_URL='http://localhost:5173',
        FRONTEND_ALLOWED_ORIGINS=[
            'http://localhost:5173',
            'http://127.0.0.1:5173',
            'http://neptune:5173',
        ],
    )
    @patch('juke_auth.views.do_auth')
    def test_social_login_uses_referer_origin_for_redirect_uri(self, mock_do_auth):
        mock_do_auth.return_value = HttpResponseRedirect('https://accounts.spotify.com/authorize')

        response = self.client.get(
            self.login_endpoint,
            HTTP_REFERER='http://neptune:5173/login',
        )

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        backend = mock_do_auth.call_args.args[0]
        self.assertEqual(
            backend.redirect_uri,
            'http://auth.local:8000/api/v1/social-auth/complete/spotify/',
        )
        self.assertEqual(
            response.wsgi_request.session.get('spotify_auth_return_to'),
            'http://neptune:5173/login',
        )
        self.assertEqual(
            response.wsgi_request.session.get('spotify_frontend_origin'),
            'http://neptune:5173',
        )
