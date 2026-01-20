import string
import re
import random

from catalog import models

REGISTRATION_VERIFY_RE = re.compile(
    "https://.*user_id=(?P<user_id>[^&amp;]*).*timestamp=(?P<timestamp>[^&amp]*).*signature=(?P<signature>.*)"
)


def create_music_resource(name: str, music_resource_cls: models.MusicResource, **kwargs) -> models.MusicResource:
    new = music_resource_cls(name=name, **kwargs)
    if not new.spotify_id:
        new.spotify_id = ''.join(random.choices(string.ascii_uppercase + string.digits, k=30))
    new.save()
    return new


def create_genre(name: str, **kwargs) -> models.Album:
    return create_music_resource(name, music_resource_cls=models.Genre, **kwargs)


def create_artist(name: str, **kwargs) -> models.Artist:
    return create_music_resource(name, music_resource_cls=models.Artist, **kwargs)


def create_album(name: str, **kwargs) -> models.Album:
    return create_music_resource(name, music_resource_cls=models.Album, **kwargs)


def create_track(name: str, **kwargs) -> models.Album:
    return create_music_resource(name, music_resource_cls=models.Track, **kwargs)
