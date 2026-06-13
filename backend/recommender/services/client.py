from __future__ import annotations

import logging
from typing import Any, Dict, List

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

ENGINE_BASE_URL = getattr(settings, 'RECOMMENDER_ENGINE_BASE_URL', None)
if not ENGINE_BASE_URL:
    raise ValueError("RECOMMENDER_ENGINE_BASE_URL must be set")
DEFAULT_TIMEOUT = int(getattr(settings, 'RECOMMENDER_ENGINE_TIMEOUT', 15))


def _request(path: str, payload: Dict[str, Any], *, request_id: str | None = None) -> Dict[str, Any]:
    url = f"{ENGINE_BASE_URL.rstrip('/')}{path}"
    logger.debug('Recommender engine request %s payload=%s', url, payload)
    kwargs = {'json': payload, 'timeout': DEFAULT_TIMEOUT}
    if request_id:
        kwargs['headers'] = {'X-Request-ID': request_id}
    response = requests.post(url, **kwargs)
    response.raise_for_status()
    data = response.json()
    logger.debug('Recommender engine response %s', data)
    return data


def fetch_recommendations(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Call the ML engine to get likeness-ranked results."""
    return _request('/recommend', profile)


def resolve_items(items: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Resolve external music identities to MLCore canonical item IDs."""
    return _request('/resolve', {'items': items})


def fetch_identity_recommendations(ranker: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """Call an MLCore ranker using external music identity seeds."""
    if ranker not in {'metadata', 'cooccurrence'}:
        raise ValueError(f"Unsupported MLCore ranker: {ranker}")
    return _request(
        f'/engine/recommend/{ranker}/identity',
        payload,
        request_id=str(payload.get('request_id') or ''),
    )


def generate_embedding(resource_type: str, attributes: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        'resource_type': resource_type,
        'attributes': attributes,
    }
    return _request('/embed', payload)


def build_vector_from_names(names: List[str]) -> Dict[str, Any]:
    return generate_embedding('text', {'tokens': names})
