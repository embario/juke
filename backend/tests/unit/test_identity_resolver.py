import datetime
import uuid

from django.test import TestCase

from catalog.models import (
    ArtistExternalIdentifier,
    GenreExternalIdentifier,
    TrackExternalIdentifier,
)
from catalog.services.identity import IdentityResolver
from tests.utils import create_album, create_artist, create_genre, create_track


class IdentityResolverTests(TestCase):

    def setUp(self):
        self.genre = create_genre(name='funk')
        self.artist = create_artist(name='Parliament')
        self.album = create_album(
            name='Mothership Connection',
            total_tracks=7,
            release_date=datetime.date(1975, 12, 15),
        )
        self.track = create_track(
            name='P. Funk',
            album=self.album,
            track_number=1,
            duration_ms=441000,
        )

    # --- juke_id precedence ---

    def test_resolve_artist_by_juke_id(self):
        found = IdentityResolver.resolve_artist(juke_id=self.artist.juke_id)
        self.assertEqual(found, self.artist)

    def test_resolve_album_by_juke_id(self):
        found = IdentityResolver.resolve_album(juke_id=self.album.juke_id)
        self.assertEqual(found, self.album)

    def test_resolve_track_by_juke_id(self):
        found = IdentityResolver.resolve_track(juke_id=self.track.juke_id)
        self.assertEqual(found, self.track)

    def test_resolve_genre_by_juke_id(self):
        found = IdentityResolver.resolve_genre(juke_id=self.genre.juke_id)
        self.assertEqual(found, self.genre)

    # --- mbid precedence ---

    def test_resolve_artist_by_mbid(self):
        self.artist.mbid = uuid.uuid4()
        self.artist.save()
        found = IdentityResolver.resolve_artist(mbid=self.artist.mbid)
        self.assertEqual(found, self.artist)

    def test_resolve_track_by_mbid(self):
        self.track.mbid = uuid.uuid4()
        self.track.save()
        found = IdentityResolver.resolve_track(mbid=self.track.mbid)
        self.assertEqual(found, self.track)

    # --- adapter precedence ---

    def test_resolve_artist_by_adapter(self):
        ArtistExternalIdentifier.objects.create(artist=self.artist, source='spotify', external_id='sp-funk-1')
        found = IdentityResolver.resolve_artist(source='spotify', external_id='sp-funk-1')
        self.assertEqual(found, self.artist)

    def test_resolve_genre_by_adapter(self):
        GenreExternalIdentifier.objects.create(genre=self.genre, source='musicbrainz', external_id='mb-funk')
        found = IdentityResolver.resolve_genre(source='musicbrainz', external_id='mb-funk')
        self.assertEqual(found, self.genre)

    # --- miss cases ---

    def test_resolve_artist_miss_juke_id(self):
        self.assertIsNone(IdentityResolver.resolve_artist(juke_id=uuid.uuid7()))

    def test_resolve_artist_miss_mbid(self):
        self.assertIsNone(IdentityResolver.resolve_artist(mbid=uuid.uuid4()))

    def test_resolve_artist_miss_adapter(self):
        self.assertIsNone(IdentityResolver.resolve_artist(source='spotify', external_id='nonexistent'))

    def test_resolve_artist_no_inputs(self):
        self.assertIsNone(IdentityResolver.resolve_artist())

    def test_resolve_artist_adapter_requires_both_source_and_external_id(self):
        ArtistExternalIdentifier.objects.create(artist=self.artist, source='spotify', external_id='partial-test')
        # source alone — falls through to None
        self.assertIsNone(IdentityResolver.resolve_artist(source='spotify'))
        # external_id alone — falls through to None
        self.assertIsNone(IdentityResolver.resolve_artist(external_id='partial-test'))

    # --- precedence ordering ---

    def test_juke_id_wins_over_mbid_and_adapter(self):
        # artist_a has mbid + adapter; artist_b has only juke_id.
        # When all three are supplied, juke_id match (artist_b) wins.
        self.artist.mbid = uuid.uuid4()
        self.artist.save()
        ArtistExternalIdentifier.objects.create(artist=self.artist, source='spotify', external_id='sp-prec')

        artist_b = create_artist(name='Funkadelic')

        found = IdentityResolver.resolve_artist(
            juke_id=artist_b.juke_id,
            mbid=self.artist.mbid,
            source='spotify',
            external_id='sp-prec',
        )
        self.assertEqual(found, artist_b)

    def test_mbid_wins_over_adapter(self):
        artist_b = create_artist(name='Funkadelic')
        artist_b.mbid = uuid.uuid4()
        artist_b.save()

        ArtistExternalIdentifier.objects.create(artist=self.artist, source='spotify', external_id='sp-mbid-prec')

        found = IdentityResolver.resolve_artist(
            mbid=artist_b.mbid,
            source='spotify',
            external_id='sp-mbid-prec',
        )
        self.assertEqual(found, artist_b)

    def test_juke_id_miss_does_not_fall_through(self):
        # Deterministic: if juke_id is supplied and misses, do NOT fall through to mbid/adapter.
        self.artist.mbid = uuid.uuid4()
        self.artist.save()
        found = IdentityResolver.resolve_artist(juke_id=uuid.uuid7(), mbid=self.artist.mbid)
        self.assertIsNone(found)

    # --- select_related efficiency ---

    def test_adapter_lookup_uses_single_query(self):
        TrackExternalIdentifier.objects.create(track=self.track, source='spotify', external_id='sp-track-q')
        with self.assertNumQueries(1):
            found = IdentityResolver.resolve_track(source='spotify', external_id='sp-track-q')
            _ = found.name  # access FK'd object attr — should not trigger extra query
