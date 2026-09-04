from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from catalog.controller import ExternalResourceStrategy
from catalog.providers import get_provider_adapter, normalize_provider
from catalog.utils import CatalogProviderUnavailable, CatalogProviderValidationError


class _FakeAdapter:
    def __init__(self, strategy):
        self.strategy = strategy

    def perform_request(self):
        return SimpleNamespace(data={'provider': 'fake'})


class CatalogProviderTests(SimpleTestCase):
    def _strategy(self, params=None):
        request = SimpleNamespace(
            path='/api/v1/artists/',
            data={},
            GET=params or {},
        )
        return ExternalResourceStrategy(request)

    def test_provider_defaults_to_spotify_for_compatibility(self):
        strategy = self._strategy({'external': 'true', 'q': 'Miles'})
        adapter = SimpleNamespace()
        with patch('catalog.controller.get_provider_adapter', return_value=adapter) as get_adapter:
            with patch.object(adapter, 'perform_request', return_value='response', create=True):
                self.assertEqual(strategy.route(), 'response')
        get_adapter.assert_called_once_with('spotify', strategy)

    def test_explicit_provider_routes_to_registered_adapter(self):
        strategy = self._strategy({'external': 'true', 'q': 'Miles', 'provider': 'apple_music'})
        with override_settings(CATALOG_PROVIDER_ADAPTERS={'apple_music': f'{__name__}._FakeAdapter'}):
            adapter = get_provider_adapter('apple_music', strategy)
        self.assertIsInstance(adapter, _FakeAdapter)
        self.assertIs(adapter.strategy, strategy)

    def test_provider_alias_is_normalized(self):
        self.assertEqual(normalize_provider('Apple-Music'), 'apple_music')

    def test_unknown_provider_is_rejected(self):
        with self.assertRaises(CatalogProviderValidationError):
            normalize_provider('not-a-provider')

    def test_recognized_but_unconfigured_provider_is_unavailable(self):
        with self.assertRaises(CatalogProviderUnavailable):
            get_provider_adapter('apple_music', self._strategy())
