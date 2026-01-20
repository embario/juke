from rest_framework import status
from rest_framework.test import APITestCase

from juke_auth.models import JukeUser, MusicProfile


class MusicProfileTests(APITestCase):
    base_url = '/api/v1/music-profiles/'

    def setUp(self):
        self.owner = JukeUser.objects.create_user(username='orbit', password='secret', email='orbit@example.com')
        self.visitor = JukeUser.objects.create_user(username='guest', password='secret', email='guest@example.com')
        self.profile = MusicProfile.objects.create(
            user=self.owner,
            display_name='Orbit Station',
            tagline='Neon ambience and synth waveforms',
            favorite_genres=['synthwave', 'ambient'],
        )

    def authenticate(self, user):
        self.client.force_login(user)

    def test_list_disabled(self):
        self.authenticate(self.owner)
        response = self.client.get(self.base_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)

    def test_me_endpoint_creates_profile(self):
        new_user = JukeUser.objects.create_user(username='new-user', password='secret', email='new@example.com')
        self.authenticate(new_user)

        response = self.client.get(f'{self.base_url}me/', format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['username'], 'new-user')
        self.assertTrue(MusicProfile.objects.filter(user=new_user).exists())

    def test_me_endpoint_updates_profile(self):
        self.authenticate(self.owner)
        payload = {
            'display_name': 'Orbit Archives',
            'tagline': 'Signals from the future',
            'favorite_genres': ['future garage', 'idm'],
        }

        response = self.client.patch(f'{self.base_url}me/', data=payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['display_name'], payload['display_name'])
        self.assertEqual(response.data['favorite_genres'], payload['favorite_genres'])

    def test_retrieve_profile_by_username(self):
        self.authenticate(self.visitor)

        response = self.client.get(f'{self.base_url}{self.owner.username}/', format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['display_name'], self.profile.display_name)
        self.assertFalse(response.data['is_owner'])

    def test_update_other_profile_forbidden(self):
        self.authenticate(self.visitor)

        response = self.client.patch(
            f'{self.base_url}{self.owner.username}/',
            data={'display_name': 'Hijacked'},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_search_returns_matches(self):
        self.authenticate(self.owner)

        response = self.client.get(f'{self.base_url}search/', {'q': 'orb'}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['username'], self.owner.username)

    def test_search_requires_authentication(self):
        response = self.client.get(f'{self.base_url}search/', {'q': 'orb'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
