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


def _request(path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    url = f"{ENGINE_BASE_URL.rstrip('/')}{path}"
    logger.debug('Recommender engine request %s payload=%s', url, payload)
    response = requests.post(url, json=payload, timeout=DEFAULT_TIMEOUT)
    response.raise_for_status()
    data = response.json()
    logger.debug('Recommender engine response %s', data)
    return data


def fetch_recommendations(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Call the ML engine to get likeness-ranked results."""
    return _request('/recommend', profile)


def generate_embedding(resource_type: str, attributes: Dict[str, Any]) -> Dict[str, Any]:
    payload = {
        'resource_type': resource_type,
        'attributes': attributes,
    }
    return _request('/embed', payload)


def build_vector_from_names(names: List[str]) -> Dict[str, Any]:
    return generate_embedding('text', {'tokens': names})
