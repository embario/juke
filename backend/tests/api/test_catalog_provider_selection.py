from rest_framework import status
from rest_framework.test import APITestCase

from catalog.models import ArtistExternalIdentifier
from juke_auth.models import JukeUser


class CatalogProviderSelectionAPITests(APITestCase):
    url = '/api/v1/artists/'

    def setUp(self):
        user = JukeUser.objects.create_user(
            username='provider-listener',
            password='pw',
            email='provider-listener@example.com',
        )
        self.client.force_login(user)

    def test_external_search_defaults_to_spotify_and_records_provenance(self):
        response = self.client.get(self.url, {'external': 'true', 'q': 'Miles'})

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data['results'][0]['provider'], 'spotify')
        self.assertTrue(response.data['results'][0]['external_id'])
        self.assertTrue(
            response.data['results'][0]['provider_url'].startswith(
                'https://open.spotify.com/artist/'
            )
        )
        identity = ArtistExternalIdentifier.objects.get(
            source='spotify',
            external_id=response.data['results'][0]['external_id'],
        )
        self.assertIsNotNone(identity.last_refreshed_at)
        self.assertIsNotNone(identity.cache_expires_at)

    def test_explicit_spotify_provider_preserves_existing_behavior(self):
        response = self.client.get(
            self.url,
            {'external': 'true', 'provider': 'spotify', 'q': 'Miles'},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(len(response.data['results']), 10)

    def test_unknown_provider_returns_validation_error(self):
        response = self.client.get(
            self.url,
            {'external': 'true', 'provider': 'unknown', 'q': 'Miles'},
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('Unsupported catalog provider', str(response.data['detail']))

    def test_recognized_unconfigured_provider_returns_service_unavailable(self):
        response = self.client.get(
            self.url,
            {'external': 'true', 'provider': 'apple_music', 'q': 'Miles'},
        )

        self.assertEqual(
            response.status_code,
            status.HTTP_503_SERVICE_UNAVAILABLE,
            response.data,
        )
        self.assertIn('recognized but not configured', str(response.data['detail']))

    def test_source_alias_can_select_provider(self):
        response = self.client.get(
            self.url,
            {'external': 'true', 'source': 'spotify', 'q': 'Miles'},
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_conflicting_provider_and_source_are_rejected(self):
        response = self.client.get(
            self.url,
            {
                'external': 'true',
                'provider': 'spotify',
                'source': 'apple_music',
                'q': 'Miles',
            },
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('provider', str(response.data['detail']))
