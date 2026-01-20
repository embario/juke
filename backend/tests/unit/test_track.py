from datetime import date

from django.db.utils import IntegrityError
from django.db import transaction
from django.test import TestCase

from catalog.models import Track, Album, Artist

from tests.utils import create_album, create_track, create_artist


class TrackTests(TestCase):

    def test_create_fail(self):
        al1 = create_album(name='some-album-1', total_tracks=10, release_date=date(year=1970, month=1, day=10))

        # No duration.
        with transaction.atomic():
            with self.assertRaises(IntegrityError):
                create_track(name='some-track-1', album=al1, track_number=1)

        create_track(name='some-track-1', album=al1, track_number=1, duration_ms=1000)

        # Same track number.
        with self.assertRaises(IntegrityError):
            create_track(name='some-track-1', album=al1, track_number=1)

    def test_create_ok(self):
        a1 = create_artist(name='some-artist-1')
        a2 = create_artist(name='some-artist-2')

        al1 = create_album(name='some-album-1', total_tracks=15, release_date=date(year=1970, month=1, day=10))
        al2 = create_album(name='some-album-2', total_tracks=1, release_date=date(year=1973, month=4, day=20))

        al1.artists.add(a1)
        al2.artists.add(a1)
        al2.artists.add(a2)

        for i in range(1, 16):
            al1.tracks.add(create_track(
                name=f"some-track-{i}",
                album=al1,
                track_number=i,
                duration_ms=1000 + i,
            ))

        al2.tracks.add(create_track(name='some-collaborative-track', album=al2, track_number=1, duration_ms=5000))

        self.assertEqual(Artist.objects.count(), 2)
        self.assertEqual(Album.objects.count(), 2)
        self.assertEqual(Track.objects.count(), 16)
        self.assertEqual(al1.artists.count(), 1)
        self.assertEqual(al2.artists.count(), 2)
        self.assertEqual(al1.tracks.count(), 15)
        self.assertEqual(al2.tracks.count(), 1)
