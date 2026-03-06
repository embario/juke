"""
Canonical identity resolution for catalog resources.

Precedence (arch §5.1):
  1. juke_id — internal global identifier (UUIDv7)
  2. mbid    — MusicBrainz canonical external identity
  3. adapter — (source, external_id) via *ExternalIdentifier tables
"""
from catalog.models import (
    Album,
    AlbumExternalIdentifier,
    Artist,
    ArtistExternalIdentifier,
    Genre,
    GenreExternalIdentifier,
    Track,
    TrackExternalIdentifier,
)


class IdentityResolver:

    @staticmethod
    def resolve_artist(*, juke_id=None, mbid=None, source=None, external_id=None) -> Artist | None:
        if juke_id:
            return Artist.objects.filter(juke_id=juke_id).first()
        if mbid:
            return Artist.objects.filter(mbid=mbid).first()
        if source and external_id:
            link = (
                ArtistExternalIdentifier.objects
                .filter(source=source, external_id=external_id)
                .select_related('artist')
                .first()
            )
            return link.artist if link else None
        return None

    @staticmethod
    def resolve_album(*, juke_id=None, mbid=None, source=None, external_id=None) -> Album | None:
        if juke_id:
            return Album.objects.filter(juke_id=juke_id).first()
        if mbid:
            return Album.objects.filter(mbid=mbid).first()
        if source and external_id:
            link = (
                AlbumExternalIdentifier.objects
                .filter(source=source, external_id=external_id)
                .select_related('album')
                .first()
            )
            return link.album if link else None
        return None

    @staticmethod
    def resolve_track(*, juke_id=None, mbid=None, source=None, external_id=None) -> Track | None:
        if juke_id:
            return Track.objects.filter(juke_id=juke_id).first()
        if mbid:
            return Track.objects.filter(mbid=mbid).first()
        if source and external_id:
            link = (
                TrackExternalIdentifier.objects
                .filter(source=source, external_id=external_id)
                .select_related('track')
                .first()
            )
            return link.track if link else None
        return None

    @staticmethod
    def resolve_genre(*, juke_id=None, source=None, external_id=None) -> Genre | None:
        if juke_id:
            return Genre.objects.filter(juke_id=juke_id).first()

        if source and external_id:
            link = (
                GenreExternalIdentifier.objects
                .filter(source=source, external_id=external_id)
                .select_related('genre')
                .first()
            )
            return link.genre if link else None
        return None
