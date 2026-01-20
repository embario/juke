import abc
import typing

from django.http import HttpRequest

from catalog.api_clients import SpotifyAPIClient


class ResourceStrategy(abc.ABC):
    def __init__(self, request: HttpRequest) -> None:
        self.request = request
        self.path = request.path
        self.data = request.data | request.GET

    @abc.abstractmethod
    def route(self) -> typing.Any:
        pass


class ExternalResourceStrategy(ResourceStrategy):
    def route(self) -> typing.Any:
        client = SpotifyAPIClient(self)
        response = client.perform_request()
        return response


class InternalResourceStrategy(ResourceStrategy):
    pass


def route(request: HttpRequest) -> typing.Any:
    strategy = ExternalResourceStrategy(request)
    response = strategy.route()
    return response
