import datetime

from django.core.exceptions import ValidationError
from django.test import TestCase

from catalog.models import Artist, ArtistExternalIdentifier
from catalog.services.provider_cache import record_provider_identity, upsert_provider_resource


class ProviderCatalogCacheTests(TestCase):
    def test_non_spotify_resource_needs_no_fabricated_spotify_id(self):
        artist, identity = upsert_provider_resource(
            resource_type='artist',
            provider='apple_music',
            external_id='203709340',
            defaults={'name': 'Nina Simone'},
            provider_data={'attributes': {'name': 'Nina Simone'}},
            provider_url='https://music.apple.com/us/artist/nina-simone/203709340',
            market='us',
            ttl_seconds=3600,
        )

        self.assertIsNone(artist.spotify_id)
        self.assertEqual(identity.artist, artist)
        self.assertEqual(identity.source, 'apple_music')
        self.assertEqual(identity.external_id, '203709340')
        self.assertEqual(identity.market, 'us')
        self.assertIsNotNone(identity.last_refreshed_at)
        self.assertIsNotNone(identity.cache_expires_at)

    def test_same_external_id_in_different_namespaces_does_not_collide(self):
        apple_artist, _ = upsert_provider_resource(
            resource_type='artist',
            provider='apple_music',
            external_id='shared-id',
            defaults={'name': 'Apple Result'},
        )
        spotify_artist, _ = upsert_provider_resource(
            resource_type='artist',
            provider='spotify',
            external_id='shared-id',
            defaults={'name': 'Spotify Result'},
        )

        self.assertNotEqual(apple_artist.juke_id, spotify_artist.juke_id)
        self.assertIsNone(apple_artist.spotify_id)
        self.assertEqual(spotify_artist.spotify_id, 'shared-id')
        self.assertEqual(ArtistExternalIdentifier.objects.count(), 2)

    def test_same_provider_identity_updates_existing_resource(self):
        original, _ = upsert_provider_resource(
            resource_type='artist',
            provider='apple_music',
            external_id='artist-1',
            defaults={'name': 'Old Name'},
        )
        refreshed, identity = upsert_provider_resource(
            resource_type='artist',
            provider='apple_music',
            external_id='artist-1',
            defaults={'name': 'New Name'},
            provider_data={'version': 2},
        )

        self.assertEqual(refreshed.pk, original.pk)
        self.assertEqual(refreshed.name, 'New Name')
        self.assertEqual(identity.provider_data, {'version': 2})

    def test_identity_cannot_be_silently_reassigned(self):
        first = Artist.objects.create(name='First')
        second = Artist.objects.create(name='Second')
        record_provider_identity(
            first,
            resource_type='artist',
            provider='apple_music',
            external_id='artist-1',
        )

        with self.assertRaises(ValidationError):
            record_provider_identity(
                second,
                resource_type='artist',
                provider='apple_music',
                external_id='artist-1',
            )

    def test_cache_expiry_uses_requested_ttl(self):
        artist = Artist.objects.create(name='Timed')
        identity = record_provider_identity(
            artist,
            resource_type='artist',
            provider='apple_music',
            external_id='timed-1',
            ttl_seconds=120,
        )
        delta = identity.cache_expires_at - identity.last_refreshed_at
        self.assertEqual(delta, datetime.timedelta(seconds=120))
