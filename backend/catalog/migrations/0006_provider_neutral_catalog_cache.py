from django.db import migrations, models


RESOURCE_LINKS = (
    ('Artist', 'ArtistExternalIdentifier', 'artist', 'artist'),
    ('Album', 'AlbumExternalIdentifier', 'album', 'album'),
    ('Track', 'TrackExternalIdentifier', 'track', 'track'),
    ('Genre', 'GenreExternalIdentifier', 'genre', None),
)


def backfill_spotify_identifiers(apps, schema_editor):
    """Make legacy Spotify identity visible through the neutral bridge tables."""
    for resource_name, identifier_name, relation_name, spotify_resource_type in RESOURCE_LINKS:
        resource_model = apps.get_model('catalog', resource_name)
        identifier_model = apps.get_model('catalog', identifier_name)
        pending = []
        queryset = resource_model.objects.exclude(spotify_id__isnull=True).exclude(spotify_id='')
        for resource in queryset.only('juke_id', 'spotify_id', 'modified_at').iterator(chunk_size=1000):
            provider_url = ''
            if spotify_resource_type:
                provider_url = f'https://open.spotify.com/{spotify_resource_type}/{resource.spotify_id}'
            pending.append(identifier_model(
                **{
                    f'{relation_name}_id': resource.juke_id,
                    'source': 'spotify',
                    'external_id': resource.spotify_id,
                    'provider_url': provider_url,
                    'last_refreshed_at': resource.modified_at,
                },
            ))
            if len(pending) == 1000:
                identifier_model.objects.bulk_create(pending, ignore_conflicts=True)
                pending = []
        if pending:
            identifier_model.objects.bulk_create(pending, ignore_conflicts=True)


def external_identifier_fields(model_name):
    return [
        migrations.AddField(
            model_name=model_name,
            name='provider_data',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name=model_name,
            name='provider_url',
            field=models.URLField(blank=True, default='', max_length=1024),
        ),
        migrations.AddField(
            model_name=model_name,
            name='market',
            field=models.CharField(blank=True, default='', max_length=32),
        ),
        migrations.AddField(
            model_name=model_name,
            name='last_refreshed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name=model_name,
            name='cache_expires_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0005_alter_album_juke_id_alter_artist_juke_id_and_more'),
    ]

    operations = [
        *external_identifier_fields('albumexternalidentifier'),
        *external_identifier_fields('artistexternalidentifier'),
        *external_identifier_fields('genreexternalidentifier'),
        *external_identifier_fields('trackexternalidentifier'),
        migrations.AlterField(
            model_name='album',
            name='spotify_id',
            field=models.CharField(blank=True, default=None, max_length=30, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='artist',
            name='spotify_id',
            field=models.CharField(blank=True, default=None, max_length=30, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='genre',
            name='spotify_id',
            field=models.CharField(blank=True, default=None, max_length=30, null=True, unique=True),
        ),
        migrations.AlterField(
            model_name='track',
            name='spotify_id',
            field=models.CharField(blank=True, default=None, max_length=30, null=True, unique=True),
        ),
        # Existing bridge rows may predate this migration, so reversing must not
        # guess which Spotify identifiers it is safe to delete.
        migrations.RunPython(backfill_spotify_identifiers, migrations.RunPython.noop),
    ]
