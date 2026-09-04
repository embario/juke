"""Catalog-provider selection and adapter construction.

Keep this registry independent of request routing so another provider can be
added without changing the catalog views or controller.
"""

from django.conf import settings
from django.utils.module_loading import import_string

from catalog.utils import CatalogProviderUnavailable, CatalogProviderValidationError


DEFAULT_PROVIDER = 'spotify'
KNOWN_PROVIDERS = ('spotify', 'apple_music')
PROVIDER_ALIASES = {
    'spotify': 'spotify',
    'apple': 'apple_music',
    'apple-music': 'apple_music',
    'apple_music': 'apple_music',
}
PROVIDER_ADAPTERS = {
    'spotify': 'catalog.api_clients.SpotifyAPIClient',
}


def normalize_provider(raw_provider) -> str:
    if raw_provider is None or not str(raw_provider).strip():
        return DEFAULT_PROVIDER
    normalized = str(raw_provider).strip().lower()
    provider = PROVIDER_ALIASES.get(normalized)
    if provider is None:
        supported = ', '.join(KNOWN_PROVIDERS)
        raise CatalogProviderValidationError(
            f"Unsupported catalog provider '{raw_provider}'. Supported providers: {supported}."
        )
    return provider


def provider_from_request_data(data) -> str:
    provider_raw = data.get('provider')
    source_raw = data.get('source')
    provider = normalize_provider(provider_raw or source_raw)
    if provider_raw and source_raw and normalize_provider(source_raw) != provider:
        raise CatalogProviderValidationError(
            "The 'provider' and 'source' selectors must identify the same catalog provider."
        )
    return provider


def get_provider_adapter(provider: str, strategy):
    configured_adapters = {
        **PROVIDER_ADAPTERS,
        **getattr(settings, 'CATALOG_PROVIDER_ADAPTERS', {}),
    }
    adapter_path = configured_adapters.get(provider)
    if adapter_path is None:
        raise CatalogProviderUnavailable(
            f"Catalog provider '{provider}' is recognized but not configured."
        )
    adapter_class = import_string(adapter_path)
    return adapter_class(strategy)
