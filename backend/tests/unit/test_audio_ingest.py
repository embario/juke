from unittest import mock

from django.test import TestCase, override_settings

from catalog.models import Artist, Album, Track
from recommender.models import TrackAudioFeatures
from recommender.services.audio_ingest import ingest_training_data


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _seed_catalog():
    """Create a minimal catalog: 2 artists (B before A alphabetically by name),
    each with one album, each album with 2 tracks.  Tracks within each album
    are inserted in reverse track_number order to verify the task sorts them.

    Artist ordering by name: "Artist A" < "Artist B"

    Genres are intentionally distinct per artist so that downstream tests
    (e.g. retrain diversity checks) have meaningful genre spread to work with.
    """
    from catalog.models import Genre

    genre_prog, _ = Genre.objects.get_or_create(spotify_id='genre:prog-rock', name='progressive rock')
    genre_jazz, _ = Genre.objects.get_or_create(spotify_id='genre:exp-jazz', name='experimental jazz')
    genre_ambient, _ = Genre.objects.get_or_create(spotify_id='genre:dark-ambient', name='dark ambient')

    artist_a = Artist.objects.create(name='Artist A', spotify_id='artist-a-id')
    artist_a.genres.add(genre_prog, genre_jazz)
    artist_b = Artist.objects.create(name='Artist B', spotify_id='artist-b-id')
    artist_b.genres.add(genre_ambient, genre_jazz)

    album_a = Album.objects.create(
        name='Album A1', spotify_id='album-a1-id',
        album_type='ALBUM', total_tracks=2, release_date='2020-01-01',
    )
    album_a.artists.add(artist_a)

    album_b = Album.objects.create(
        name='Album B1', spotify_id='album-b1-id',
        album_type='ALBUM', total_tracks=2, release_date='2021-06-15',
    )
    album_b.artists.add(artist_b)

    # Insert track 2 before track 1 to prove the task sorts by track_number.
    Track.objects.create(
        name='A-Track-2', spotify_id='a-track-2', album=album_a,
        track_number=2, disc_number=1, duration_ms=200000, explicit=False,
    )
    Track.objects.create(
        name='A-Track-1', spotify_id='a-track-1', album=album_a,
        track_number=1, disc_number=1, duration_ms=180000, explicit=False,
    )
    Track.objects.create(
        name='B-Track-2', spotify_id='b-track-2', album=album_b,
        track_number=2, disc_number=1, duration_ms=220000, explicit=False,
    )
    Track.objects.create(
        name='B-Track-1', spotify_id='b-track-1', album=album_b,
        track_number=1, disc_number=1, duration_ms=190000, explicit=False,
    )

    return {
        'artists': [artist_a, artist_b],
        'albums': [album_a, album_b],
        'tracks': {
            'a1': Track.objects.get(spotify_id='a-track-1'),
            'a2': Track.objects.get(spotify_id='a-track-2'),
            'b1': Track.objects.get(spotify_id='b-track-1'),
            'b2': Track.objects.get(spotify_id='b-track-2'),
        },
    }


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@override_settings(SPOTIFY_USE_STUB_DATA=True)
class IngestTrainingDataTests(TestCase):
    def setUp(self):
        self.catalog = _seed_catalog()

    # --- basic completion --------------------------------------------------

    def test_ingests_all_tracks(self):
        result = ingest_training_data()

        self.assertEqual(result.ingested, 4)
        self.assertEqual(result.skipped, 0)
        self.assertEqual(result.failed, 0)
        self.assertEqual(TrackAudioFeatures.objects.count(), 4)

    def test_audio_features_fields_populated(self):
        ingest_training_data()

        af = TrackAudioFeatures.objects.get(track__spotify_id='a-track-1')
        # Stub produces deterministic values; just verify they are in plausible ranges.
        self.assertGreaterEqual(af.energy, 0.0)
        self.assertLessEqual(af.energy, 1.0)
        self.assertGreaterEqual(af.tempo, 60.0)
        self.assertLessEqual(af.tempo, 200.0)
        self.assertIn(af.mode, ('major', 'minor'))
        self.assertGreaterEqual(af.key, 0)
        self.assertLessEqual(af.key, 11)
        self.assertGreaterEqual(af.loudness, -60.0)
        self.assertLessEqual(af.loudness, 0.0)

    # --- DFS ordering -------------------------------------------------------

    @mock.patch('recommender.services.audio_ingest._fetch_audio_features')
    def test_processes_artists_alphabetically(self, mock_fetch):
        """Track the order in which spotify_ids arrive at _fetch_audio_features."""
        call_order: list[list[str]] = []

        def capture(track_ids):
            call_order.append(list(track_ids))
            # Return valid stub payloads so the upsert succeeds.
            from catalog import spotify_stub
            return spotify_stub.audio_features(track_ids)

        mock_fetch.side_effect = capture
        ingest_training_data()

        # All 4 tracks fit in one batch (< 50), so we get two calls:
        # first Artist A's album, then Artist B's album.
        self.assertEqual(len(call_order), 2)

        # Within Artist A's batch: track_number 1 before 2.
        self.assertEqual(call_order[0], ['a-track-1', 'a-track-2'])
        # Within Artist B's batch: track_number 1 before 2.
        self.assertEqual(call_order[1], ['b-track-1', 'b-track-2'])

    # --- resume / skip ------------------------------------------------------

    def test_skips_already_ingested_tracks(self):
        # Pre-populate one track's audio features.
        track_a1 = self.catalog['tracks']['a1']
        TrackAudioFeatures.objects.create(
            track=track_a1,
            energy=0.5, valence=0.5, tempo=120.0, key=5, mode='minor',
            danceability=0.5, acousticness=0.5, instrumentalness=0.5,
            liveness=0.1, speechiness=0.1, loudness=-20.0, time_signature=4,
        )

        result = ingest_training_data()

        self.assertEqual(result.ingested, 3)
        self.assertEqual(result.skipped, 1)
        self.assertEqual(result.failed, 0)
        # Total rows unchanged for the pre-existing track (no duplicate created).
        self.assertEqual(TrackAudioFeatures.objects.count(), 4)

    def test_resume_is_idempotent(self):
        """Running twice produces no duplicates and skips everything on second run."""
        result1 = ingest_training_data()
        result2 = ingest_training_data()

        self.assertEqual(result1.ingested, 4)
        self.assertEqual(result2.ingested, 0)
        self.assertEqual(result2.skipped, 4)
        self.assertEqual(TrackAudioFeatures.objects.count(), 4)

    # --- failure handling ---------------------------------------------------

    @mock.patch('recommender.services.audio_ingest._fetch_audio_features')
    def test_batch_fetch_failure_logs_and_continues(self, mock_fetch):
        """If the Spotify call fails for one album's batch, the other album still runs."""
        call_count = {'n': 0}

        def fail_first_succeed_rest(track_ids):
            call_count['n'] += 1
            if call_count['n'] == 1:
                raise Exception('Spotify rate limit')
            from catalog import spotify_stub
            return spotify_stub.audio_features(track_ids)

        mock_fetch.side_effect = fail_first_succeed_rest
        result = ingest_training_data()

        # First batch (Artist A, 2 tracks) failed; second batch (Artist B) succeeded.
        self.assertEqual(result.failed, 2)
        self.assertEqual(result.ingested, 2)
        self.assertEqual(len(result.failed_track_ids), 2)
        self.assertIn('a-track-1', result.failed_track_ids)
        self.assertIn('a-track-2', result.failed_track_ids)

    @mock.patch('recommender.services.audio_ingest._fetch_audio_features')
    def test_missing_track_in_response_counted_as_failure(self, mock_fetch):
        """If Spotify returns None for a track ID, it's a per-track failure."""
        def drop_one(track_ids):
            from catalog import spotify_stub
            results = spotify_stub.audio_features(track_ids)
            # Drop the first item to simulate a missing track.
            return [None] + results[1:]

        mock_fetch.side_effect = drop_one
        result = ingest_training_data()

        # Each album batch loses its first track → 2 failures, 2 successes.
        self.assertEqual(result.failed, 2)
        self.assertEqual(result.ingested, 2)
