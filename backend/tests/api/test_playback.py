from unittest.mock import patch

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from social_django.models import UserSocialAuth

from juke_auth.models import JukeUser


class PlaybackAPITests(APITestCase):
    playback_url = '/api/v1/playback/'

    def setUp(self):
        self.user = JukeUser.objects.create_user(username='listener', email='listener@example.com', password='pass1234')
        self.client.force_login(self.user)
        self.social = UserSocialAuth.objects.create(
            user=self.user,
            provider='spotify',
            uid='spotify-user',
            extra_data={
                'access_token': 'initial-token',
                'refresh_token': 'refresh-token',
                'expires_at': timezone.now().timestamp() + 3600,
            },
        )

    def _playback_payload(self):
        return {
            'is_playing': True,
            'progress_ms': 9000,
            'item': {
                'id': 'track-123',
                'uri': 'spotify:track:track-123',
                'name': 'Forty Six & 2',
                'duration_ms': 300000,
                'album': {
                    'id': 'album-1',
                    'uri': 'spotify:album:album-1',
                    'name': 'Ænima',
                    'images': [{'url': 'https://images.example/cover.jpg'}],
                },
                'artists': [
                    {
                        'id': 'artist-1',
                        'uri': 'spotify:artist:artist-1',
                        'name': 'TOOL',
                    }
                ],
            },
            'device': {
                'id': 'device-1',
                'name': 'Safari',
                'type': 'Computer',
                'volume_percent': 70,
                'is_active': True,
            },
        }

    def test_requires_authentication(self):
        self.client.logout()
        response = self.client.post(f'{self.playback_url}play/', data={'track_uri': 'spotify:track:123'})
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_missing_linked_provider_returns_error(self):
        self.social.delete()
        response = self.client.post(f'{self.playback_url}play/', data={'track_uri': 'spotify:track:123'})
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Link a streaming account', response.data['detail'])

    @patch('catalog.services.playback.spotipy.Spotify')
    def test_can_start_playback(self, mock_spotify):
        client = mock_spotify.return_value
        client.current_playback.return_value = self._playback_payload()

        response = self.client.post(
            f'{self.playback_url}play/',
            data={'track_uri': 'spotify:track:123', 'device_id': 'device-abc'},
        )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        client.start_playback.assert_called_with(device_id='device-abc', uris=['spotify:track:123'])
        self.assertEqual(response.data['track']['name'], 'Forty Six & 2')
        self.assertEqual(response.data['device']['name'], 'Safari')

    @patch('catalog.services.playback.spotipy.Spotify')
    def test_can_pause_and_fetch_state(self, mock_spotify):
        client = mock_spotify.return_value
        client.current_playback.return_value = self._playback_payload()

        response = self.client.post(f'{self.playback_url}pause/', data={'device_id': 'device-1'})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        client.pause_playback.assert_called_with(device_id='device-1')
        self.assertTrue(response.data['is_playing'])

    @patch('catalog.services.playback.spotipy.Spotify')
    def test_state_endpoint_returns_no_content_when_idle(self, mock_spotify):
        client = mock_spotify.return_value
        client.current_playback.return_value = None

        response = self.client.get(f'{self.playback_url}state/', data={'provider': 'spotify'})
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

    @patch('catalog.services.playback.spotipy.Spotify')
    def test_next_and_previous_controls(self, mock_spotify):
        client = mock_spotify.return_value
        client.current_playback.return_value = self._playback_payload()

        next_response = self.client.post(f'{self.playback_url}next/', data={'device_id': 'device-1'})
        prev_response = self.client.post(f'{self.playback_url}previous/', data={'device_id': 'device-1'})

        self.assertEqual(next_response.status_code, status.HTTP_200_OK)
        self.assertEqual(prev_response.status_code, status.HTTP_200_OK)
        client.next_track.assert_called_with(device_id='device-1')
        client.previous_track.assert_called_with(device_id='device-1')
