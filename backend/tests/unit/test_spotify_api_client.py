from types import SimpleNamespace

from django.test import SimpleTestCase, override_settings

from catalog.api_clients import SpotifyAPIClient
from catalog.utils import StreamingAPIError


@override_settings(SPOTIFY_USE_STUB_DATA=True)
class SpotifyAPIClientTests(SimpleTestCase):
    def setUp(self):
        self.strategy = SimpleNamespace(request=SimpleNamespace())

    def _build_client(self):
        return SpotifyAPIClient(strategy=self.strategy)

    def test_prepare_path_requires_query_for_search_endpoints(self):
        client = self._build_client()

        with self.assertRaises(StreamingAPIError):
            client.prepare_path('/api/v1/artists/', {})

    def test_prepare_data_sets_type_and_uri_for_detail_requests(self):
        client = self._build_client()

        data = client.prepare_data('/api/v1/artists/123/', {})

        self.assertEqual(data['type'], 'artist')
        self.assertEqual(data['uri'], 'spotify:artist:123')
        self.assertEqual(data['offset'], 0)

    def test_prepare_data_preserves_search_query(self):
        client = self._build_client()

        payload = client.prepare_data('/api/v1/tracks/', {'q': 'Lateralus'})

        self.assertEqual(payload['type'], 'track')
        self.assertEqual(payload['q'], 'Lateralus')
        self.assertEqual(payload['offset'], 0)
        self.assertNotIn('uri', payload)

    def test_prepare_data_rejects_unknown_resources(self):
        client = self._build_client()

        with self.assertRaises(StreamingAPIError):
            client.prepare_data('/api/v1/genres/', {'q': 'ambient'})
