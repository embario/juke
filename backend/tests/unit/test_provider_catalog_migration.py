from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase


class ProviderCatalogMigrationTests(TransactionTestCase):
    migrate_from = ('catalog', '0005_alter_album_juke_id_alter_artist_juke_id_and_more')
    migrate_to = ('catalog', '0006_provider_neutral_catalog_cache')

    def setUp(self):
        super().setUp()
        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_from])
        old_apps = executor.loader.project_state([self.migrate_from]).apps
        Artist = old_apps.get_model('catalog', 'Artist')
        self.legacy_artist = Artist.objects.create(
            name='Legacy Spotify Artist',
            spotify_id='legacy-spotify-id',
        )

        executor = MigrationExecutor(connection)
        executor.migrate([self.migrate_to])
        self.apps = executor.loader.project_state([self.migrate_to]).apps

    def tearDown(self):
        MigrationExecutor(connection).migrate([self.migrate_to])
        super().tearDown()

    def test_migration_backfills_spotify_bridge_and_allows_provider_only_rows(self):
        Artist = self.apps.get_model('catalog', 'Artist')
        ArtistExternalIdentifier = self.apps.get_model(
            'catalog',
            'ArtistExternalIdentifier',
        )

        legacy = Artist.objects.get(pk=self.legacy_artist.pk)
        identity = ArtistExternalIdentifier.objects.get(
            source='spotify',
            external_id='legacy-spotify-id',
        )
        self.assertEqual(identity.artist_id, legacy.juke_id)
        self.assertEqual(
            identity.provider_url,
            'https://open.spotify.com/artist/legacy-spotify-id',
        )
        self.assertIsNotNone(identity.last_refreshed_at)

        provider_only = Artist.objects.create(name='Provider-only Artist')
        self.assertIsNone(provider_only.spotify_id)
