import time
from unittest.mock import patch

from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase
from social_django.models import UserSocialAuth

from juke_auth.models import JukeUser
from juke_auth.views import SpotifyTokenIssueThrottle


class SpotifyCredentialBrokerAPITests(APITestCase):
    status_url = '/api/v1/auth/spotify/status/'
    token_url = '/api/v1/auth/spotify/token/'
    disconnect_url = '/api/v1/auth/spotify/disconnect/'

    def setUp(self):
        self.user = JukeUser.objects.create_user(
            username='spotify-broker',
            email='spotify-broker@example.com',
            password='pass1234',
        )
        self.token, _ = Token.objects.get_or_create(user=self.user)

    def authenticate(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

    def test_status_requires_authentication(self):
        response = self.client.get(self.status_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_status_returns_not_connected_when_no_spotify_link(self):
        self.authenticate()

        response = self.client.get(self.status_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data['connected'])
        self.assertEqual(response.data['provider'], 'spotify')
        self.assertIsNone(response.data['spotify_user_id'])
        self.assertEqual(response.data['scopes'], [])

    def test_status_returns_link_metadata_when_connected(self):
        self.authenticate()
        UserSocialAuth.objects.create(
            user=self.user,
            provider='spotify',
            uid='spotify-user-1',
            extra_data={
                'access_token': 'token-1',
                'refresh_token': 'refresh-1',
                'scope': 'user-read-playback-state user-modify-playback-state',
                'expires_at': time.time() + 300,
            },
        )

        response = self.client.get(self.status_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertTrue(response.data['connected'])
        self.assertEqual(response.data['spotify_user_id'], 'spotify-user-1')
        self.assertTrue(response.data['has_refresh_token'])
        self.assertIn('user-read-playback-state', response.data['scopes'])

    def test_token_issue_requires_connected_spotify_account(self):
        self.authenticate()

        response = self.client.post(self.token_url)

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['error'], 'spotify_not_connected')

    def test_token_issue_returns_access_token_without_refresh_token(self):
        self.authenticate()
        UserSocialAuth.objects.create(
            user=self.user,
            provider='spotify',
            uid='spotify-user-2',
            extra_data={
                'access_token': 'access-2',
                'refresh_token': 'refresh-2',
                'expires_at': time.time() + 600,
            },
        )

        response = self.client.post(self.token_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['provider'], 'spotify')
        self.assertEqual(response.data['token_type'], 'Bearer')
        self.assertEqual(response.data['access_token'], 'access-2')
        self.assertNotIn('refresh_token', response.data)
        self.assertGreaterEqual(response.data['expires_in'], 0)

    @patch('social_django.models.UserSocialAuth.refresh_token')
    def test_token_issue_refreshes_expired_credentials(self, mock_refresh_token):
        self.authenticate()
        account = UserSocialAuth.objects.create(
            user=self.user,
            provider='spotify',
            uid='spotify-user-3',
            extra_data={
                'access_token': 'stale-access',
                'refresh_token': 'refresh-3',
                'expires_at': time.time() - 1,
            },
        )

        def fake_refresh(strategy):
            account.extra_data = {
                **(account.extra_data or {}),
                'access_token': 'fresh-access',
                'expires_at': time.time() + 3600,
            }
            account.save(update_fields=['extra_data'])

        mock_refresh_token.side_effect = fake_refresh

        response = self.client.post(self.token_url)

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['access_token'], 'fresh-access')
        mock_refresh_token.assert_called_once()
        account.refresh_from_db()
        self.assertEqual(account.extra_data.get('access_token'), 'fresh-access')

    def test_disconnect_removes_spotify_social_account(self):
        self.authenticate()
        UserSocialAuth.objects.create(
            user=self.user,
            provider='spotify',
            uid='spotify-user-4',
            extra_data={'access_token': 'token-4'},
        )

        response = self.client.post(self.disconnect_url)

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(UserSocialAuth.objects.filter(user=self.user, provider='spotify').exists())

    @patch.object(SpotifyTokenIssueThrottle, 'scope', 'spotify_token_issue_test', create=True)
    @patch.object(SpotifyTokenIssueThrottle, 'rate', '1/min', create=True)
    def test_token_issue_is_throttled_when_rate_limit_exceeded(self):
        self.authenticate()
        UserSocialAuth.objects.create(
            user=self.user,
            provider='spotify',
            uid='spotify-user-5',
            extra_data={
                'access_token': 'access-5',
                'refresh_token': 'refresh-5',
                'expires_at': time.time() + 600,
            },
        )

        first_response = self.client.post(self.token_url)
        second_response = self.client.post(self.token_url)

        self.assertEqual(first_response.status_code, status.HTTP_200_OK)
        self.assertEqual(second_response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
