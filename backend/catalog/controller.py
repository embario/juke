import abc
import typing

from django.http import HttpRequest

from catalog.providers import get_provider_adapter, provider_from_request_data


class ResourceStrategy(abc.ABC):
    def __init__(self, request: HttpRequest) -> None:
        self.request = request
        self.path = request.path
        request_data = request.data.dict() if hasattr(request.data, 'dict') else dict(request.data)
        query_data = request.GET.dict() if hasattr(request.GET, 'dict') else dict(request.GET)
        self.data = request_data | query_data

    @abc.abstractmethod
    def route(self) -> typing.Any:
        pass


class ExternalResourceStrategy(ResourceStrategy):
    def route(self) -> typing.Any:
        provider = provider_from_request_data(self.data)
        client = get_provider_adapter(provider, self)
        response = client.perform_request()
        return response


class InternalResourceStrategy(ResourceStrategy):
    pass


def route(request: HttpRequest) -> typing.Any:
    strategy = ExternalResourceStrategy(request)
    response = strategy.route()
    return response
