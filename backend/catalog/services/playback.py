from __future__ import annotations

import abc
import logging
import time
from typing import Any, Dict, Optional

from django.utils import timezone
from rest_framework.exceptions import APIException
from social_django.models import UserSocialAuth
from social_django.utils import load_strategy
import spotipy
from spotipy.exceptions import SpotifyException

logger = logging.getLogger(__name__)


class PlaybackError(APIException):
    status_code = 400
    default_detail = 'Unable to control playback at this time.'
    default_code = 'playback_error'


class PlaybackProviderNotLinked(PlaybackError):
    default_detail = 'Connect a streaming provider to control playback.'
    default_code = 'playback_provider_not_linked'


class UnsupportedPlaybackProvider(PlaybackError):
    default_detail = 'The requested playback provider is not supported.'
    default_code = 'playback_provider_unsupported'


class PlaybackProviderFailure(PlaybackError):
    default_detail = 'The playback provider failed to process the request.'
    default_code = 'playback_provider_failure'


class PlaybackProvider(abc.ABC):
    slug: str
    social_provider: Optional[str] = None

    def __init__(self, user, social_account: Optional[UserSocialAuth] = None) -> None:
        self.user = user
        self.social_account = social_account

    @abc.abstractmethod
    def play(self, *, track_uri: Optional[str], context_uri: Optional[str], position_ms: Optional[int], device_id: Optional[str]) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def pause(self, *, device_id: Optional[str]) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def next(self, *, device_id: Optional[str]) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def previous(self, *, device_id: Optional[str]) -> None:
        raise NotImplementedError

    @abc.abstractmethod
    def state(self) -> Optional[Dict[str, Any]]:
        raise NotImplementedError


class PlaybackService:
    def __init__(self, user, provider: Optional[str] = None) -> None:
        self.user = user
        self.provider_slug = self._resolve_provider_slug(provider)
        provider_cls = PROVIDER_REGISTRY[self.provider_slug]
        social_account = self._get_social_account(provider_cls)
        self.provider = provider_cls(user=user, social_account=social_account)

    def _resolve_provider_slug(self, requested: Optional[str]) -> str:
        if requested:
            if requested not in PROVIDER_REGISTRY:
                raise UnsupportedPlaybackProvider(f"Provider '{requested}' is not supported.")
            return requested

        for slug, provider_cls in PROVIDER_REGISTRY.items():
            social_name = provider_cls.social_provider
            if social_name and hasattr(self.user, 'social_auth'):
                if self.user.social_auth.filter(provider=social_name).exists():
                    return slug
        raise PlaybackProviderNotLinked('Link a streaming account to control playback.')

    def _get_social_account(self, provider_cls: type[PlaybackProvider]) -> Optional[UserSocialAuth]:
        social_name = provider_cls.social_provider
        if not social_name:
            return None
        if not hasattr(self.user, 'social_auth'):
            raise PlaybackProviderNotLinked('Streaming accounts are not connected for this user.')
        account = self.user.social_auth.filter(provider=social_name).first()
        logger.info(
            'Resolved social account for user %s provider %s: %s',
            getattr(self.user, 'pk', self.user),
            social_name,
            account.pk if account else None,
        )
        if not account:
            raise PlaybackProviderNotLinked(f"Link your {provider_cls.slug.title()} account to control playback.")
        return account

    def play(
        self,
        *,
        track_uri: Optional[str],
        context_uri: Optional[str],
        position_ms: Optional[int],
        device_id: Optional[str],
    ) -> Optional[Dict[str, Any]]:
        self.provider.play(
            track_uri=track_uri,
            context_uri=context_uri,
            position_ms=position_ms,
            device_id=device_id,
        )
        return self.provider.state()

    def pause(self, *, device_id: Optional[str]) -> Optional[Dict[str, Any]]:
        self.provider.pause(device_id=device_id)
        return self.provider.state()

    def next(self, *, device_id: Optional[str]) -> Optional[Dict[str, Any]]:
        self.provider.next(device_id=device_id)
        return self.provider.state()

    def previous(self, *, device_id: Optional[str]) -> Optional[Dict[str, Any]]:
        self.provider.previous(device_id=device_id)
        return self.provider.state()

    def state(self) -> Optional[Dict[str, Any]]:
        return self.provider.state()


class SpotifyPlaybackProvider(PlaybackProvider):
    slug = 'spotify'
    social_provider = 'spotify'
    TOKEN_SKEW_SECONDS = 45

    def __init__(self, user, social_account: Optional[UserSocialAuth] = None) -> None:
        super().__init__(user, social_account)
        self.strategy = load_strategy()

    def _require_social_account(self) -> UserSocialAuth:
        if not self.social_account:
            raise PlaybackProviderNotLinked('Link your Spotify account to control playback.')
        return self.social_account

    def _ensure_access_token(self) -> str:
        account = self._require_social_account()
        data = account.extra_data or {}
        token = data.get('access_token')
        expires_at = data.get('expires_at') or data.get('expires')
        now = time.time()

        if expires_at:
            try:
                expires_ts = float(expires_at)
            except (TypeError, ValueError):
                expires_ts = 0
            if expires_ts - self.TOKEN_SKEW_SECONDS <= now:
                self._refresh_token(account)
                data = account.extra_data or {}
                token = data.get('access_token')

        if not token:
            raise PlaybackProviderNotLinked('Spotify authentication expired. Please reconnect your account.')
        return token

    def _refresh_token(self, account: UserSocialAuth) -> None:
        refresh_token = account.extra_data.get('refresh_token') if account.extra_data else None
        if not refresh_token:
            raise PlaybackProviderNotLinked('Spotify authentication is missing a refresh token.')
        try:
            account.refresh_token(self.strategy)
            account.refresh_from_db()
            self.social_account = account
        except Exception as exc:  # pylint: disable=broad-except
            response_detail = ''
            response = getattr(exc, 'response', None)
            if response is not None:
                try:
                    response_detail = response.text
                except Exception:  # pragma: no cover - best effort logging
                    response_detail = ''
            logger.error('Unable to refresh Spotify token: %s %s', exc, response_detail)
            raise PlaybackProviderNotLinked('Spotify authentication expired. Please reconnect your account.') from exc

    def _client(self) -> spotipy.Spotify:
        token = self._ensure_access_token()
        return spotipy.Spotify(auth=token)

    def _execute(self, operation):
        attempts = 0
        while True:
            client = self._client()
            try:
                return operation(client)
            except SpotifyException as exc:
                token_invalid = exc.http_status == 401 and attempts == 0
                if token_invalid:
                    logger.info('Spotify token expired for user %s; attempting refresh.', getattr(self.user, 'pk', self.user))
                    self._refresh_token(self._require_social_account())
                    attempts += 1
                    continue
                playback_not_found = exc.http_status == 404 and exc.code == -1
                if playback_not_found:
                    logger.info('Spotify reports no active playback: %s', exc)
                    return None
                logger.error('Spotify playback error: %s', exc)
                raise PlaybackProviderFailure(exc.msg or 'Spotify playback request failed.') from exc

    def play(self, *, track_uri: Optional[str], context_uri: Optional[str], position_ms: Optional[int], device_id: Optional[str]) -> None:
        kwargs: Dict[str, Any] = {}
        if device_id:
            kwargs['device_id'] = device_id
        if track_uri:
            kwargs['uris'] = [track_uri]
        elif context_uri:
            kwargs['context_uri'] = context_uri
        if position_ms is not None:
            kwargs['position_ms'] = position_ms
        self._execute(lambda client: client.start_playback(**kwargs))

    def pause(self, *, device_id: Optional[str]) -> None:
        kwargs = {'device_id': device_id} if device_id else {}
        self._execute(lambda client: client.pause_playback(**kwargs))

    def next(self, *, device_id: Optional[str]) -> None:
        kwargs = {'device_id': device_id} if device_id else {}
        self._execute(lambda client: client.next_track(**kwargs))

    def previous(self, *, device_id: Optional[str]) -> None:
        kwargs = {'device_id': device_id} if device_id else {}
        self._execute(lambda client: client.previous_track(**kwargs))

    def state(self) -> Optional[Dict[str, Any]]:
        playback = self._execute(lambda client: client.current_playback())
        if not playback:
            return None
        track = playback.get('item')
        device = playback.get('device')
        normalized: Dict[str, Any] = {
            'provider': self.slug,
            'is_playing': bool(playback.get('is_playing')),
            'progress_ms': playback.get('progress_ms') or 0,
            'updated_at': timezone.now().isoformat(),
            'track': self._normalize_track(track),
            'device': self._normalize_device(device),
        }
        return normalized

    def _normalize_track(self, track: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not track:
            return None
        album = track.get('album') or {}
        artists = track.get('artists') or []
        images = album.get('images') or []
        artwork_url = None
        if isinstance(images, list) and images:
            artwork = images[0]
            if isinstance(artwork, dict):
                artwork_url = artwork.get('url')
        return {
            'id': track.get('id'),
            'uri': track.get('uri'),
            'name': track.get('name'),
            'duration_ms': track.get('duration_ms'),
            'album': {
                'id': album.get('id'),
                'uri': album.get('uri'),
                'name': album.get('name'),
            } if album else None,
            'artists': [
                {
                    'id': artist.get('id'),
                    'uri': artist.get('uri'),
                    'name': artist.get('name'),
                }
                for artist in artists
                if isinstance(artist, dict)
            ],
            'artwork_url': artwork_url,
        }

    def _normalize_device(self, device: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        if not device:
            return None
        return {
            'id': device.get('id'),
            'name': device.get('name'),
            'type': device.get('type'),
            'volume_percent': device.get('volume_percent'),
            'is_active': device.get('is_active'),
        }


PROVIDER_REGISTRY: Dict[str, type[PlaybackProvider]] = {
    SpotifyPlaybackProvider.slug: SpotifyPlaybackProvider,
}
