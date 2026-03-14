from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings


def _normalize_origin(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
        return None
    return urlunsplit((parsed.scheme, parsed.netloc, '', '', '')).rstrip('/')


def _coerce_iterable(value: object) -> Iterable[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [str(entry) for entry in value]
    return [str(value)]


def get_allowed_frontend_origins() -> list[str]:
    configured = list(_coerce_iterable(getattr(settings, 'FRONTEND_ALLOWED_ORIGINS', [])))
    if not configured:
        configured = [
            getattr(settings, 'FRONTEND_URL', ''),
            *getattr(settings, 'CORS_ALLOWED_ORIGINS', []),
        ]

    normalized: list[str] = []
    seen: set[str] = set()
    for candidate in configured:
        origin = _normalize_origin(candidate)
        if not origin or origin in seen:
            continue
        normalized.append(origin)
        seen.add(origin)
    return normalized


def get_request_frontend_origin(request) -> str | None:
    if request is None:
        return None

    allowed = set(get_allowed_frontend_origins())
    for header_name in ('HTTP_ORIGIN', 'HTTP_REFERER'):
        origin = _normalize_origin(request.META.get(header_name))
        if origin and origin in allowed:
            return origin
    return None


def get_frontend_origin(request=None, fallback: str | None = None) -> str | None:
    request_origin = get_request_frontend_origin(request)
    if request_origin:
        return request_origin

    fallback_origin = _normalize_origin(fallback)
    if fallback_origin:
        return fallback_origin

    configured_frontend = _normalize_origin(getattr(settings, 'FRONTEND_URL', None))
    if configured_frontend:
        return configured_frontend

    allowed = get_allowed_frontend_origins()
    return allowed[0] if allowed else None


def build_frontend_url(path: str, request=None, fallback: str | None = None) -> str:
    parts = urlsplit(path)
    origin = get_frontend_origin(request=request, fallback=fallback)
    if origin is None:
        return path

    normalized_path = parts.path or '/'
    if not normalized_path.startswith('/'):
        normalized_path = f'/{normalized_path}'

    origin_parts = urlsplit(origin)
    return urlunsplit(
        (
            origin_parts.scheme,
            origin_parts.netloc,
            normalized_path,
            parts.query,
            parts.fragment,
        )
    )


def is_allowed_frontend_url(candidate: str | None) -> bool:
    origin = _normalize_origin(candidate)
    return bool(origin and origin in set(get_allowed_frontend_origins()))


def append_query_params(url: str, params: dict[str, str]) -> str:
    parts = urlsplit(url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update({key: value for key, value in params.items() if value is not None})
    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(query),
            parts.fragment,
        )
    )


def build_frontend_verification_url(signer) -> str:
    base_url = build_frontend_url(
        signer.get_base_url(),
        request=signer.request,
    )
    signed_url = append_query_params(
        base_url,
        {key: str(value) for key, value in signer.get_signed_data().items()},
    )
    return signed_url
