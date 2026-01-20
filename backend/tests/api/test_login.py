from unittest.mock import patch

from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework.authtoken.models import Token

from social_core.backends.spotify import SpotifyOAuth2

from juke_auth.models import JukeUser


class LoginTests(APITestCase):
    social_login_url = '/api/v1/auth/social-login/'

    @patch.object(SpotifyOAuth2, 'do_auth')
    def test_social_login_create_user(self, mock_auth):
        mock_auth.side_effect = lambda x, expires=None: JukeUser.objects.create(username='social_user', password='pwd')
        self.assertEqual(JukeUser.objects.count(), 0)

        resp = self.client.post(self.social_login_url, data={
            'access_token': 'TOKEN'
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIsNotNone(resp.data['token'])
        token = resp.data['token']
        self.assertEqual(Token.objects.count(), 1)
        self.assertEqual(JukeUser.objects.count(), 1)
        self.assertTrue(Token.objects.filter(key=token).exists())
        self.assertTrue(JukeUser.objects.filter(username='social_user').exists())
        self.assertEqual(JukeUser.objects.get(username='social_user').auth_token.key, token)

    @patch.object(SpotifyOAuth2, 'do_auth')
    def test_social_login_existing_user(self, mock_auth):
        exp_user = JukeUser.objects.create(username='social_user', password='pwd')
        mock_auth.return_value = exp_user
        self.assertEqual(JukeUser.objects.count(), 1)

        resp = self.client.post(self.social_login_url, data={
            'access_token': 'TOKEN'
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(JukeUser.objects.count(), 1)
        self.assertEqual(Token.objects.count(), 1)
        self.assertIsNotNone(resp.data['token'])
        token = resp.data['token']
        self.assertTrue(Token.objects.filter(key=token).exists())
        self.assertTrue(JukeUser.objects.filter(username='social_user').exists())
        self.assertEqual(JukeUser.objects.get(username='social_user').auth_token.key, token)

    def test_social_login_no_access_token(self):
        resp = self.client.post(self.social_login_url, data={}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data['detail'], "'access_token' is required.")

    @patch.object(SpotifyOAuth2, 'do_auth')
    def test_social_login_failed(self, mock_auth):
        mock_auth.side_effect = ConnectionError("Something bad happened.")

        resp = self.client.post(self.social_login_url, data={
            'access_token': 'Something valid.',
        }, format='json')

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(resp.data['detail'], 'Something bad happened.')
