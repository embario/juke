from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase
from social_django.models import UserSocialAuth

from juke_auth.models import JukeUser
from powerhour.models import PowerHourSession


class PowerHourSessionStartTests(APITestCase):
    def setUp(self):
        self.user = JukeUser.objects.create_user(
            username='session-admin',
            email='session-admin@example.com',
            password='pass1234',
        )
        self.token, _ = Token.objects.get_or_create(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

        self.session = PowerHourSession.objects.create(
            admin=self.user,
            title='Session With Spotify Gate',
        )

    @property
    def start_url(self):
        return f'/api/v1/powerhour/sessions/{self.session.id}/start/'

    def test_start_requires_spotify_connection(self):
        response = self.client.post(self.start_url, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data.get('error'), 'spotify_not_connected')
        self.assertIn('Connect Spotify', response.data.get('detail', ''))

    def test_start_without_tracks_still_fails_after_spotify_is_connected(self):
        UserSocialAuth.objects.create(
            user=self.user,
            provider='spotify',
            uid='spotify-user-1',
            extra_data={
                'access_token': 'spotify-access-token',
                'expires_at': timezone.now().timestamp() + 3600,
            },
        )

        response = self.client.post(self.start_url, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data.get('detail'), 'Add at least one track before starting.')
