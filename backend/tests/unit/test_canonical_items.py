import uuid

from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase

from catalog.models import TrackExternalIdentifier
from mlcore.models import CanonicalItemAlias
from mlcore.services.canonical_items import (
    ALIAS_RESOURCE_RECORDING,
    ALIAS_RESOURCE_TRACK,
    ALIAS_SOURCE_MUSICBRAINZ,
    ALIAS_SOURCE_SPOTIFY,
    ITEM_TYPE_RECORDING_MBID,
    ITEM_TYPE_RECORDING_MSID,
    ITEM_TYPE_SPOTIFY_TRACK,
    bulk_ensure_canonical_items_for_tracks,
    identity_from_listenbrainz_candidates,
    materialize_track_aliases,
)
from tests.utils import create_album, create_track


class CanonicalItemIdentityTests(SimpleTestCase):

    def test_prefers_recording_mbid_over_other_ids(self):
        recording_mbid = uuid.uuid4()

        identity = identity_from_listenbrainz_candidates(
            recording_mbid=str(recording_mbid),
            recording_msid='recording-msid',
            spotify_id='spotify-track-id',
        )

        self.assertIsNotNone(identity)
        self.assertEqual(identity.item_type, ITEM_TYPE_RECORDING_MBID)
        self.assertEqual(identity.canonical_key, f'{ITEM_TYPE_RECORDING_MBID}:{recording_mbid}')

    def test_prefers_recording_msid_over_spotify(self):
        identity = identity_from_listenbrainz_candidates(
            recording_msid='recording-msid',
            spotify_id='spotify-track-id',
        )

        self.assertIsNotNone(identity)
        self.assertEqual(identity.item_type, ITEM_TYPE_RECORDING_MSID)
        self.assertEqual(identity.canonical_key, f'{ITEM_TYPE_RECORDING_MSID}:recording-msid')

    def test_falls_back_to_spotify(self):
        identity = identity_from_listenbrainz_candidates(
            spotify_id='spotify-track-id',
        )

        self.assertIsNotNone(identity)
        self.assertEqual(identity.item_type, ITEM_TYPE_SPOTIFY_TRACK)
        self.assertEqual(identity.canonical_key, f'{ITEM_TYPE_SPOTIFY_TRACK}:spotify-track-id')


class CanonicalItemAliasModelTests(TestCase):

    def setUp(self):
        self.album = create_album(name='Album', total_tracks=10, release_date='2026-01-01')
        self.track = create_track(name='Track', album=self.album, track_number=1, duration_ms=1000)
        self.canonical_item = bulk_ensure_canonical_items_for_tracks([self.track])[self.track.juke_id]

    def test_alias_unique_by_source_resource_and_source_id(self):
        CanonicalItemAlias.objects.create(
            canonical_item=self.canonical_item,
            source=ALIAS_SOURCE_SPOTIFY,
            resource_type=ALIAS_RESOURCE_TRACK,
            source_id='sp-track',
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CanonicalItemAlias.objects.create(
                    canonical_item=self.canonical_item,
                    source=ALIAS_SOURCE_SPOTIFY,
                    resource_type=ALIAS_RESOURCE_TRACK,
                    source_id='sp-track',
                )

    def test_alias_cascades_when_canonical_item_is_deleted(self):
        CanonicalItemAlias.objects.create(
            canonical_item=self.canonical_item,
            source=ALIAS_SOURCE_SPOTIFY,
            resource_type=ALIAS_RESOURCE_TRACK,
            source_id='sp-track',
        )

        self.canonical_item.delete()

        self.assertEqual(CanonicalItemAlias.objects.count(), 0)


class CanonicalItemAliasMaterializationTests(TestCase):

    def setUp(self):
        self.album = create_album(name='Album', total_tracks=10, release_date='2026-01-01')

    def test_creates_spotify_and_musicbrainz_aliases_for_track(self):
        mbid = uuid.uuid4()
        track = create_track(
            name='Track',
            album=self.album,
            track_number=1,
            duration_ms=1000,
            spotify_id='spotify-a',
            mbid=mbid,
        )

        result = materialize_track_aliases([track], source_version='test-corpus')

        self.assertEqual(result.created_count, 2)
        canonical_item = bulk_ensure_canonical_items_for_tracks([track])[track.juke_id]
        spotify_alias = CanonicalItemAlias.objects.get(
            source=ALIAS_SOURCE_SPOTIFY,
            resource_type=ALIAS_RESOURCE_TRACK,
            source_id='spotify-a',
        )
        mbid_alias = CanonicalItemAlias.objects.get(
            source=ALIAS_SOURCE_MUSICBRAINZ,
            resource_type=ALIAS_RESOURCE_RECORDING,
            source_id=str(mbid),
        )
        self.assertEqual(spotify_alias.canonical_item, canonical_item)
        self.assertEqual(mbid_alias.canonical_item, canonical_item)
        self.assertEqual(canonical_item.item_type, ITEM_TYPE_RECORDING_MBID)
        self.assertEqual(spotify_alias.source_version, 'test-corpus')

    def test_creates_track_external_identifier_aliases(self):
        track = create_track(
            name='Track',
            album=self.album,
            track_number=1,
            duration_ms=1000,
            spotify_id='spotify-b',
        )
        TrackExternalIdentifier.objects.create(
            track=track,
            source='musicbrainz',
            external_id='external-recording',
        )

        materialize_track_aliases([track])

        alias = CanonicalItemAlias.objects.get(
            source='musicbrainz',
            resource_type=ALIAS_RESOURCE_TRACK,
            source_id='external-recording',
        )
        self.assertEqual(alias.canonical_item, bulk_ensure_canonical_items_for_tracks([track])[track.juke_id])

    def test_materialization_is_idempotent(self):
        track = create_track(
            name='Track',
            album=self.album,
            track_number=1,
            duration_ms=1000,
            spotify_id='spotify-c',
        )

        first = materialize_track_aliases([track])
        second = materialize_track_aliases([track])

        self.assertEqual(first.created_count, 1)
        self.assertEqual(second.created_count, 0)
        self.assertEqual(second.existing_count, 1)
        self.assertEqual(CanonicalItemAlias.objects.count(), 1)

    def test_conflict_is_reported_without_reassigning_existing_alias(self):
        first = create_track(
            name='First',
            album=self.album,
            track_number=1,
            duration_ms=1000,
            spotify_id='spotify-first',
        )
        second = create_track(
            name='Second',
            album=self.album,
            track_number=2,
            duration_ms=1000,
            spotify_id='spotify-second',
        )
        first_canonical = bulk_ensure_canonical_items_for_tracks([first])[first.juke_id]
        second_canonical = bulk_ensure_canonical_items_for_tracks([second])[second.juke_id]
        CanonicalItemAlias.objects.create(
            canonical_item=first_canonical,
            source=ALIAS_SOURCE_SPOTIFY,
            resource_type=ALIAS_RESOURCE_TRACK,
            source_id='spotify-second',
        )

        result = materialize_track_aliases([second])

        self.assertEqual(result.conflict_count, 1)
        alias = CanonicalItemAlias.objects.get(
            source=ALIAS_SOURCE_SPOTIFY,
            resource_type=ALIAS_RESOURCE_TRACK,
            source_id='spotify-second',
        )
        self.assertEqual(alias.canonical_item, first_canonical)
        self.assertNotEqual(alias.canonical_item, second_canonical)
