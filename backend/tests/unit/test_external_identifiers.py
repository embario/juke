import datetime
import uuid

from django.db import IntegrityError
from django.test import TestCase

from catalog.models import (
    AlbumExternalIdentifier,
    Artist,
    ArtistExternalIdentifier,
    Genre,
    GenreExternalIdentifier,
    TrackExternalIdentifier,
)
from tests.utils import create_album, create_artist, create_genre, create_track


class ExternalIdentifierTests(TestCase):

    def setUp(self):
        self.genre = create_genre(name='jazz')
        self.artist = create_artist(name='Miles Davis')
        self.album = create_album(
            name='Kind of Blue',
            total_tracks=5,
            release_date=datetime.date(1959, 8, 17),
        )
        self.track = create_track(
            name='So What',
            album=self.album,
            track_number=1,
            duration_ms=545000,
        )

    def test_juke_id_auto_populated_and_unique(self):
        self.assertIsNotNone(self.artist.juke_id)
        self.assertIsNotNone(self.album.juke_id)
        self.assertIsNotNone(self.track.juke_id)
        self.assertIsNotNone(self.genre.juke_id)
        # uuid7 values should be distinct across models/instances
        ids = {self.artist.juke_id, self.album.juke_id, self.track.juke_id, self.genre.juke_id}
        self.assertEqual(len(ids), 4)

    def test_juke_id_is_uuidv7(self):
        # RFC 9562 UUIDv7: version == 7
        self.assertEqual(self.artist.juke_id.version, 7)

    def test_create_external_identifier_for_each_resource(self):
        ArtistExternalIdentifier.objects.create(artist=self.artist, source='spotify', external_id='sp-artist-1')
        AlbumExternalIdentifier.objects.create(album=self.album, source='apple_music', external_id='am-album-1')
        TrackExternalIdentifier.objects.create(track=self.track, source='youtube_music', external_id='yt-track-1')
        GenreExternalIdentifier.objects.create(genre=self.genre, source='musicbrainz', external_id='mb-genre-1')

        self.assertEqual(self.artist.external_ids.count(), 1)
        self.assertEqual(self.album.external_ids.count(), 1)
        self.assertEqual(self.track.external_ids.count(), 1)
        self.assertEqual(self.genre.external_ids.count(), 1)

    def test_unique_together_source_external_id(self):
        ArtistExternalIdentifier.objects.create(artist=self.artist, source='spotify', external_id='dup-id')
        other_artist = create_artist(name='John Coltrane')
        with self.assertRaises(IntegrityError):
            ArtistExternalIdentifier.objects.create(artist=other_artist, source='spotify', external_id='dup-id')

    def test_same_external_id_different_source_allowed(self):
        ArtistExternalIdentifier.objects.create(artist=self.artist, source='spotify', external_id='xyz')
        ArtistExternalIdentifier.objects.create(artist=self.artist, source='apple_music', external_id='xyz')
        self.assertEqual(self.artist.external_ids.count(), 2)

    def test_fk_references_juke_id(self):
        link = ArtistExternalIdentifier.objects.create(artist=self.artist, source='spotify', external_id='fk-test')
        # Stored FK column value should be the juke_id (UUID), not the auto-PK integer.
        self.assertEqual(link.artist_id, self.artist.juke_id)
        self.assertIsInstance(link.artist_id, uuid.UUID)

    def test_cascade_delete(self):
        ArtistExternalIdentifier.objects.create(artist=self.artist, source='spotify', external_id='will-die')
        self.assertEqual(ArtistExternalIdentifier.objects.count(), 1)
        self.artist.delete()
        self.assertEqual(ArtistExternalIdentifier.objects.count(), 0)

    def test_mbid_nullable_on_artist_album_track(self):
        self.assertIsNone(self.artist.mbid)
        self.assertIsNone(self.album.mbid)
        self.assertIsNone(self.track.mbid)
        # Genre has no mbid
        self.assertFalse(hasattr(Genre, 'mbid'))

    def test_mbid_assignable(self):
        mb = uuid.uuid4()
        self.artist.mbid = mb
        self.artist.save()
        self.assertEqual(Artist.objects.get(pk=self.artist.pk).mbid, mb)
