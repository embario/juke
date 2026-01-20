import typing
import abc
import logging

from django.conf import settings
from django.http import HttpRequest
from rest_framework.exceptions import ParseError

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from catalog.utils import APIResponse, StreamingAPIError
from catalog import serializers, spotify_stub


logger = logging.getLogger(__name__)
ResourceStrategy = typing.TypeVar('ResourceStrategy')


class StreamingPlatformAPIClient(abc.ABC):
    def __init__(self, strategy: ResourceStrategy) -> None:
        self.strategy = strategy
        self.client: typing.Any = None
        self.request: HttpRequest = strategy.request

    def perform_request(self):
        external_url = self.prepare_path(self.strategy.path, self.strategy.data)
        data = self.prepare_data(external_url, self.strategy.data)

        try:
            resp = self._perform_request(external_url, data)
        except ParseError as e:
            logger.error(e)
            raise

        return resp

    @abc.abstractmethod
    def prepare_path(self, path: str, data: dict) -> dict:
        """ Prepares Path for API Request."""
        pass

    @abc.abstractmethod
    def prepare_data(self, path: str, data: dict) -> dict:
        """ Prepares Data for API Request."""
        pass

    @abc.abstractmethod
    def _perform_request(self, path: str, data: dict) -> dict:
        """ Perform Request to Platform API. """
        pass


class SpotifyAPIClient(StreamingPlatformAPIClient):
    """ API Client for Spotify (using Spotipy)."""

    def __init__(self, strategy: ResourceStrategy) -> None:
        super().__init__(strategy)
        self.use_stub = getattr(settings, 'SPOTIFY_USE_STUB_DATA', False)
        self.client = None if self.use_stub else spotipy.Spotify(
            client_credentials_manager=SpotifyClientCredentials()
        )

    def prepare_path(self, path: str, data: dict) -> str:
        if 'q' not in data and path in ['/api/v1/artists/', '/api/v1/albums', '/api/v1/tracks/']:
            raise StreamingAPIError("Missing search parameter 'q'.")
        return path

    def prepare_data(self, path: str, data: dict) -> dict:
        # Populate type
        if 'artists' in path:
            data['type'] = 'artist'
        elif 'albums' in path:
            data['type'] = 'album'
        elif 'track' in path:
            data['type'] = 'track'
        else:
            raise StreamingAPIError()

        if 'q' not in data:
            spotify_id = path.split("/")[-2]
            data['uri'] = f"spotify:{data['type']}:{spotify_id}"

        # Offset data
        if 'offset' not in data:
            data['offset'] = 0
        return data

    def _perform_request(self, path: str, data: str) -> APIResponse:
        if self.use_stub:
            res = self._perform_stub_request(data)
        else:
            if 'q' in data:
                res = self.client.search(data['q'], type=data['type'], offset=data['offset'])
                res = res[f"{data['type']}s"]
            elif data['type'] == 'artist':
                res = self.client.artist(data['uri'])
            elif data['type'] == 'album':
                res = self.client.album(data['uri'])
            elif data['type'] == 'track':
                res = self.client.track(data['uri'])
            else:
                raise StreamingAPIError()

        response = APIResponse(res)
        ser = {
            'artist': serializers.SpotifyArtistSerializer,
            'album': serializers.SpotifyAlbumSerializer,
            'track': serializers.SpotifyTrackSerializer,
        }[data['type']]

        # Deserialize into actual MusicResource instances for saving to DB,
        # but keep serialized versions for response.
        for idx, item in enumerate(response):
            ser_instance = ser(data=item, context={'request': self.request})
            ser_instance.is_valid(raise_exception=True)
            ser_instance.save()
            response._data[idx] = ser_instance.data
            response.instance = ser_instance.instance
        return response

    def _perform_stub_request(self, data: dict) -> dict:
        if 'q' in data:
            return spotify_stub.search_response(data['type'])

        if data['type'] == 'artist':
            return spotify_stub.artist_detail(data['uri'])
        if data['type'] == 'album':
            return spotify_stub.album_detail(data['uri'])
        if data['type'] == 'track':
            return spotify_stub.track_detail(data['uri'])

        raise StreamingAPIError()
