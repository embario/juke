from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

from django.conf import settings
from django.contrib.auth import get_user_model, login
from django.core.cache import cache
from django.utils import timezone

from social_django.strategy import DjangoStrategy


@dataclass
class CachedState:
    user_id: Optional[int]
    expires_at: float

    @classmethod
    def from_payload(cls, payload: Dict[str, Any]) -> "CachedState":
        return cls(
            user_id=payload.get("user_id"),
            expires_at=payload.get("expires_at", 0),
        )

    def to_payload(self) -> Dict[str, Any]:
        return {"user_id": self.user_id, "expires_at": self.expires_at}


class ResilientStrategy(DjangoStrategy):
    """Extends the default strategy to fall back when session cookies vanish."""

    state_cache_prefix = getattr(settings, "SOCIAL_AUTH_STATE_CACHE_PREFIX", "social-state")
    state_cache_ttl = int(getattr(settings, "SOCIAL_AUTH_STATE_CACHE_TTL", 600))

    def session_set(self, name: str, value: Any):
        super().session_set(name, value)
        if name.endswith("_state") and value:
            self._persist_state(name, value)

    def session_get(self, name: str, default: Any = None):
        value = super().session_get(name, default)
        if value is None and name.endswith("_state"):
            value = self._restore_state(name)
        return value if value is not None else default

    # Internal helpers -------------------------------------------------

    def _persist_state(self, name: str, value: str) -> None:
        cache_key = self._state_cache_key(name, value)
        expires_at = timezone.now().timestamp() + self.state_cache_ttl
        user_id = self.request.user.id if self.request.user.is_authenticated else None
        cache.set(cache_key, {"user_id": user_id, "expires_at": expires_at}, self.state_cache_ttl)

    def _restore_state(self, name: str) -> Optional[str]:
        request_state = self._request_state()
        if not request_state:
            return None
        cache_key = self._state_cache_key(name, request_state)
        payload = cache.get(cache_key)
        if not payload:
            return None
        cache.delete(cache_key)
        cached_state = CachedState.from_payload(payload)
        self.session[name] = request_state
        if cached_state.user_id and not self.request.user.is_authenticated:
            UserModel = get_user_model()
            try:
                user = UserModel.objects.get(pk=cached_state.user_id)
            except UserModel.DoesNotExist:  # pragma: no cover - best effort
                return request_state
            login(self.request, user)
        return request_state

    def _request_state(self) -> Optional[str]:
        return self.request.GET.get("state") or self.request.POST.get("state")

    def _state_cache_key(self, name: str, state_value: str) -> str:
        backend = name[: -len("_state")]
        return f"{self.state_cache_prefix}:{backend}:{state_value}"
