import typing
from rest_framework.exceptions import APIException


class StreamingAPIError(APIException):
    status_code = 400
    default_detail = "Service cannot satisfy request because it is not available through the Streaming Platform API."
    default_code = "streaming_api_error"


class APIResponse:
    def __init__(self, data) -> None:
        self.href = data.get('href')
        self.limit = data.get('limit')
        self.count = data.get('count') or data.get('total')
        self.offset = data.get('offset')
        self.previous = data.get('previous')
        self.multi_resource = isinstance(data.get('items'), list)
        self.instance: typing.Any = None

        if self.multi_resource:
            self._data = data['items']
        else:
            self._data = [data]

    @property
    def data(self) -> dict:
        return self._data[0] if not self.multi_resource else {
            'href': self.href,
            'results': self._data,
            'limit': self.limit,
            'count': self.count,
            'offset': self.offset,
            'previous': self.previous,
        }

    def __iter__(self) -> typing.Any:
        return iter(self._data)
