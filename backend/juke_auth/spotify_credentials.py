from __future__ import annotations

from dataclasses import dataclass
import logging
import time
from typing import Any, Iterable

from social_django.models import UserSocialAuth
from social_django.utils import load_strategy


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SpotifyAccessToken:
    value: str
    expires_at: float | None
    token_type: str = "Bearer"

    def expires_in(self) -> int | None:
        if self.expires_at is None:
            return None
        return max(int(self.expires_at - time.time()), 0)


class SpotifyCredentialError(Exception):
    def __init__(self, detail: str, code: str = "spotify_credentials_invalid") -> None:
        super().__init__(detail)
        self.detail = detail
        self.code = code


class SpotifyCredentialBroker:
    PROVIDER = "spotify"
    TOKEN_SKEW_SECONDS = 45

    def __init__(self, user, strategy: Any | None = None) -> None:
        self.user = user
        self.strategy = strategy or load_strategy()

    def social_account(self) -> UserSocialAuth | None:
        return (
            UserSocialAuth.objects.filter(user=self.user, provider=self.PROVIDER)
            .order_by("-id")
            .first()
        )

    def status(self) -> dict[str, Any]:
        account = self.social_account()
        if not account:
            return {
                "connected": False,
                "provider": self.PROVIDER,
                "spotify_user_id": None,
                "scopes": [],
                "expires_at": None,
                "expires_in": None,
                "has_refresh_token": False,
            }

        data = account.extra_data or {}
        expires_at = self._extract_expires_at(data)
        return {
            "connected": True,
            "provider": self.PROVIDER,
            "spotify_user_id": account.uid,
            "scopes": self._extract_scopes(data),
            "expires_at": int(expires_at) if expires_at is not None else None,
            "expires_in": self._expires_in(expires_at),
            "has_refresh_token": bool(data.get("refresh_token")),
        }

    def disconnect(self) -> int:
        deleted_count, _ = UserSocialAuth.objects.filter(
            user=self.user,
            provider=self.PROVIDER,
        ).delete()
        return deleted_count

    def issue_access_token(self, force_refresh: bool = False) -> SpotifyAccessToken:
        account = self.social_account()
        if not account:
            raise SpotifyCredentialError(
                "Connect Spotify before requesting a streaming token.",
                code="spotify_not_connected",
            )

        data = account.extra_data or {}
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        expires_at = self._extract_expires_at(data)

        should_refresh = False
        now = time.time()
        if refresh_token:
            if not access_token:
                should_refresh = True
            elif force_refresh:
                should_refresh = True
            elif expires_at is not None and expires_at - self.TOKEN_SKEW_SECONDS <= now:
                should_refresh = True

        if should_refresh:
            self._refresh(account)
            account.refresh_from_db()
            data = account.extra_data or {}
            access_token = data.get("access_token")
            expires_at = self._extract_expires_at(data)

        if not access_token:
            raise SpotifyCredentialError(
                "Spotify authentication expired. Please reconnect your account.",
                code="spotify_access_token_unavailable",
            )

        return SpotifyAccessToken(value=access_token, expires_at=expires_at)

    def _refresh(self, account: UserSocialAuth) -> None:
        try:
            account.refresh_token(self.strategy)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning(
                "Failed to refresh spotify token for user %s",
                getattr(self.user, "pk", self.user),
                exc_info=exc,
            )
            raise SpotifyCredentialError(
                "Spotify authentication expired. Please reconnect your account.",
                code="spotify_refresh_failed",
            ) from exc

    def _extract_scopes(self, data: dict[str, Any]) -> list[str]:
        raw_scopes: Any = data.get("scope") or data.get("scopes") or []
        if isinstance(raw_scopes, str):
            scopes: Iterable[str] = raw_scopes.replace(",", " ").split()
        elif isinstance(raw_scopes, (list, tuple, set)):
            scopes = [str(scope) for scope in raw_scopes]
        else:
            scopes = []
        return sorted({scope.strip() for scope in scopes if str(scope).strip()})

    def _extract_expires_at(self, data: dict[str, Any]) -> float | None:
        raw = data.get("expires_at") or data.get("expires")
        if raw in (None, ""):
            return None
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    def _expires_in(self, expires_at: float | None) -> int | None:
        if expires_at is None:
            return None
        return max(int(expires_at - time.time()), 0)
