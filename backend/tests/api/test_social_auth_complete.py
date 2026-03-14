from unittest.mock import patch

from django.http import HttpResponseRedirect
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase
from social_core.exceptions import AuthConnectionError


class SocialAuthCompleteTests(APITestCase):
    complete_url = '/api/v1/social-auth/complete/spotify/'

    @override_settings(FRONTEND_URL='http://frontend.local')
    @patch('juke_auth.views.do_complete')
    def test_spotify_complete_connection_error_redirect(self, mock_do_complete):
        mock_do_complete.side_effect = AuthConnectionError(None, 'Spotify unavailable')

        resp = self.client.get(self.complete_url)

        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertEqual(
            resp['Location'],
            'http://frontend.local/login?error=spotify_unavailable',
        )

    @patch('juke_auth.views.do_complete')
    def test_spotify_complete_connection_error_json(self, mock_do_complete):
        mock_do_complete.side_effect = AuthConnectionError(None, 'Spotify unavailable')

        resp = self.client.get(self.complete_url, HTTP_ACCEPT='application/json')

        self.assertEqual(resp.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(resp.json()['error'], 'spotify_unavailable')

    @override_settings(FRONTEND_URL='http://frontend.local')
    @patch('juke_auth.views.do_complete')
    def test_spotify_complete_generic_error_redirect(self, mock_do_complete):
        mock_do_complete.side_effect = RuntimeError('boom')

        resp = self.client.get(self.complete_url)

        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertEqual(
            resp['Location'],
            'http://frontend.local/login?error=spotify_auth_failed',
        )

    @override_settings(
        PUBLIC_BACKEND_URL='http://auth.local:8000',
        FRONTEND_URL='http://localhost:5173',
        FRONTEND_ALLOWED_ORIGINS=[
            'http://localhost:5173',
            'http://127.0.0.1:5173',
            'http://neptune:5173',
        ],
    )
    @patch('juke_auth.views.do_complete')
    def test_spotify_complete_error_redirect_uses_session_frontend_origin(self, mock_do_complete):
        mock_do_complete.side_effect = AuthConnectionError(None, 'Spotify unavailable')
        session = self.client.session
        session['spotify_frontend_origin'] = 'http://neptune:5173'
        session.save()

        resp = self.client.get(self.complete_url)

        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertEqual(
            resp['Location'],
            'http://neptune:5173/login?error=spotify_unavailable',
        )

    @override_settings(
        PUBLIC_BACKEND_URL='http://auth.local:8000',
        FRONTEND_URL='http://localhost:5173',
        FRONTEND_ALLOWED_ORIGINS=[
            'http://localhost:5173',
            'http://127.0.0.1:5173',
            'http://neptune:5173',
        ],
    )
    @patch('juke_auth.views.do_complete')
    def test_spotify_complete_uses_session_origin_for_redirect_uri_and_final_redirect(self, mock_do_complete):
        mock_do_complete.return_value = HttpResponseRedirect('http://unused')
        session = self.client.session
        session['spotify_frontend_origin'] = 'http://neptune:5173'
        session['spotify_auth_return_to'] = 'http://neptune:5173/world'
        session.save()

        resp = self.client.get(self.complete_url)

        backend = mock_do_complete.call_args.args[0]
        self.assertEqual(
            backend.redirect_uri,
            'http://auth.local:8000/api/v1/social-auth/complete/spotify/',
        )
        self.assertEqual(resp.status_code, status.HTTP_302_FOUND)
        self.assertEqual(resp['Location'], 'http://neptune:5173/world')
