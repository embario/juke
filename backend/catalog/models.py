import datetime

from django.core.exceptions import ValidationError
from django.db import models

CHOICES_ALBUM_TYPE = (
    ('ALBUM', 'Album'),
    ('SINGLE', 'Single'),
    ('COMPILATION', 'Compilation'),
)


class MusicResource(models.Model):
    """ Generic class for all music-related resource models. """
    spotify_id = models.CharField(max_length=30, blank=False, null=False, unique=True, default=None)
    created_at = models.DateTimeField(auto_now_add=True)
    modified_at = models.DateTimeField(auto_now=True)
    spotify_data = models.JSONField(null=True, default=dict)
    custom_data = models.JSONField(null=True, default=dict)

    class Meta:
        abstract = True

    def __repr__(self):
        return f"<{self.__class__.__name__}: {self.name}>"


class Genre(MusicResource):
    name = models.CharField(unique=True, blank=False, null=False, max_length=512)


class Artist(MusicResource):
    name = models.CharField(blank=False, null=False, max_length=512)
    genres = models.ManyToManyField(Genre, related_name='artists')


def _normalize_release_date(raw_value, precision=None):
    """Spotify sometimes sends YYYY or YYYY-MM for albums; coerce to a real date."""
    if isinstance(raw_value, datetime.date):
        return raw_value

    if not raw_value:
        raise ValidationError("Album release_date is required.")

    if precision is None:
        if len(raw_value) == 4:
            precision = 'year'
        elif len(raw_value) == 7:
            precision = 'month'
        else:
            precision = 'day'

    try:
        if precision == 'year':
            return datetime.date(int(raw_value), 1, 1)
        if precision == 'month':
            year, month = raw_value.split('-')
            return datetime.date(int(year), int(month), 1)
        return datetime.date.fromisoformat(raw_value)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Invalid release_date value from external source.") from exc


class Album(MusicResource):
    name = models.CharField(blank=False, null=False, max_length=1024)
    artists = models.ManyToManyField(Artist, related_name='albums')
    album_type = models.CharField(
        blank=False,
        null=False,
        default=CHOICES_ALBUM_TYPE[0][0],
        choices=CHOICES_ALBUM_TYPE,
        max_length=12,
    )

    total_tracks = models.IntegerField(null=False)
    release_date = models.DateField(null=False)

    @staticmethod
    def get_or_create_with_validated_data(data):
        release_date = _normalize_release_date(
            data['release_date'],
            data.get('release_date_precision'),
        )
        try:
            instance = Album.objects.get(
                name=data['name'],
                spotify_id=data['id'],
            )

            instance.name = data['name']
            instance.spotify_id = data['id']
            instance.total_tracks = data['total_tracks']
            instance.release_date = release_date
            instance.save()
            created = False

        except Album.DoesNotExist:
            instance = Album.objects.create(
                name=data['name'],
                spotify_id=data['id'],
                album_type=data['album_type'].upper(),
                total_tracks=data['total_tracks'],
                release_date=release_date,
            )
            created = True
        return instance, created


class Track(MusicResource):
    name = models.CharField(blank=False, null=False, max_length=1024)
    album = models.ForeignKey(Album, related_name='tracks', on_delete=models.PROTECT)
    track_number = models.IntegerField(null=False)
    disc_number = models.IntegerField(null=False, default=1)
    duration_ms = models.IntegerField(null=False)
    explicit = models.BooleanField(null=False, default=False)

    class Meta:
        unique_together = ('album', 'track_number')

    @staticmethod
    def get_or_create_with_validated_data(album, data):
        try:
            instance = Track.objects.get(
                name=data['name'],
                spotify_id=data['id'],
            )

            instance.name = data['name']
            instance.spotify_id = data['id']
            instance.track_number = data['track_number']
            instance.disc_number = data['disc_number']
            instance.duration_ms = data['duration_ms']
            instance.explicit = data['explicit']
            created = False

        except Track.DoesNotExist:
            instance = Track.objects.create(
                name=data['name'],
                album=album,
                spotify_id=data['id'],
                track_number=data['track_number'],
                disc_number=data['disc_number'],
                duration_ms=data['duration_ms'],
                explicit=data['explicit']
            )
            created = True
        return instance, created


class ImageResource(models.Model):
    url = models.CharField(null=False, blank=False, max_length=1024)

    class Meta:
        abstract = True


class ArtistImageResource(models.Model):
    image = models.ImageField(upload_to='static/media/artists/')
    artist = models.ForeignKey(Artist, related_name='images', on_delete=models.PROTECT)


class AlbumImageResource(models.Model):
    image = models.ImageField(upload_to='static/media/albums/')
    album = models.ForeignKey(Album, related_name='images', on_delete=models.PROTECT)
