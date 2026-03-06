import datetime
import uuid

from django.core.exceptions import ValidationError
from django.db import models

CHOICES_ALBUM_TYPE = (
    ('ALBUM', 'Album'),
    ('SINGLE', 'Single'),
    ('COMPILATION', 'Compilation'),
)

EXTERNAL_ID_SOURCES = (
    ('spotify', 'Spotify'),
    ('apple_music', 'Apple Music'),
    ('youtube_music', 'YouTube Music'),
    ('musicbrainz', 'MusicBrainz'),
)


class MusicResource(models.Model):
    """ Generic class for all music-related resource models. """
    juke_id = models.UUIDField(unique=True, null=False, default=uuid.uuid7, editable=False)
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
    mbid = models.UUIDField(null=True, blank=True, db_index=True)


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
    mbid = models.UUIDField(null=True, blank=True, db_index=True)

    @staticmethod
    def get_or_create_with_validated_data(data):
        release_date = _normalize_release_date(
            data['release_date'],
            data.get('release_date_precision'),
        )
        defaults = {
            'name': data['name'],
            'album_type': data.get('album_type', CHOICES_ALBUM_TYPE[0][0]).upper(),
            'total_tracks': data['total_tracks'],
            'release_date': release_date,
        }
        instance, created = Album.objects.update_or_create(
            spotify_id=data['id'],
            defaults=defaults,
        )
        return instance, created


class Track(MusicResource):
    name = models.CharField(blank=False, null=False, max_length=1024)
    album = models.ForeignKey(Album, related_name='tracks', on_delete=models.PROTECT)
    track_number = models.IntegerField(null=False)
    disc_number = models.IntegerField(null=False, default=1)
    duration_ms = models.IntegerField(null=False)
    explicit = models.BooleanField(null=False, default=False)
    mbid = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        unique_together = ('album', 'track_number')

    @staticmethod
    def get_or_create_with_validated_data(album, data):
        defaults = {
            'name': data['name'],
            'album': album,
            'track_number': data['track_number'],
            'disc_number': data.get('disc_number', 1),
            'duration_ms': data['duration_ms'],
            'explicit': data.get('explicit', False),
        }
        instance, created = Track.objects.update_or_create(
            spotify_id=data['id'],
            defaults=defaults,
        )
        return instance, created


class ExternalIdentifier(models.Model):
    """Maps external provider IDs onto canonical catalog resources (via juke_id FK)."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.CharField(max_length=32, choices=EXTERNAL_ID_SOURCES)
    external_id = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True
        unique_together = ('source', 'external_id')


class GenreExternalIdentifier(ExternalIdentifier):
    genre = models.ForeignKey(Genre, to_field='juke_id', on_delete=models.CASCADE, related_name='external_ids')

    class Meta(ExternalIdentifier.Meta):
        db_table = 'catalog_genre_external_id'


class ArtistExternalIdentifier(ExternalIdentifier):
    artist = models.ForeignKey(Artist, to_field='juke_id', on_delete=models.CASCADE, related_name='external_ids')

    class Meta(ExternalIdentifier.Meta):
        db_table = 'catalog_artist_external_id'


class AlbumExternalIdentifier(ExternalIdentifier):
    album = models.ForeignKey(Album, to_field='juke_id', on_delete=models.CASCADE, related_name='external_ids')

    class Meta(ExternalIdentifier.Meta):
        db_table = 'catalog_album_external_id'


class TrackExternalIdentifier(ExternalIdentifier):
    track = models.ForeignKey(Track, to_field='juke_id', on_delete=models.CASCADE, related_name='external_ids')

    class Meta(ExternalIdentifier.Meta):
        db_table = 'catalog_track_external_id'


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


class SearchHistory(models.Model):
    """
    Tracks user search queries and the resources they engaged with.
    Used for analytics and future personalization features.
    """
    user = models.ForeignKey('juke_auth.JukeUser', on_delete=models.CASCADE, related_name='search_history')
    search_query = models.CharField(max_length=500, blank=False, null=False)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
        ]
        verbose_name_plural = 'Search histories'

    def __str__(self):
        return f"{self.user.username}: '{self.search_query}' at {self.timestamp}"


class SearchHistoryResource(models.Model):
    """
    Records individual resources that a user clicked during a search session.
    """
    RESOURCE_TYPE_CHOICES = [
        ('genre', 'Genre'),
        ('artist', 'Artist'),
        ('album', 'Album'),
        ('track', 'Track'),
    ]

    search_history = models.ForeignKey(
        SearchHistory,
        related_name='engaged_resources',
        on_delete=models.CASCADE
    )
    resource_type = models.CharField(
        max_length=20,
        choices=RESOURCE_TYPE_CHOICES,
        blank=False,
        null=False
    )
    resource_id = models.IntegerField(blank=False, null=False)
    resource_name = models.CharField(max_length=500, blank=False, null=False)

    class Meta:
        indexes = [
            models.Index(fields=['search_history', 'resource_type']),
        ]

    def __str__(self):
        return f"{self.resource_type}: {self.resource_name} (ID: {self.resource_id})"
