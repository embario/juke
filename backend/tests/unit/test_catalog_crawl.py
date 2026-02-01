from unittest import mock

from django.test import TestCase, override_settings

from catalog.models import Artist, Album, Track
from catalog.services.catalog_crawl import crawl_catalog


# ---------------------------------------------------------------------------
# Constants derived from the stub behaviour
# ---------------------------------------------------------------------------

# search_response('artist') returns 10 artists (stub-artist-0 … stub-artist-9).
# Every genre seed returns the *same* 10 artists, so after dedup only 10 are
# crawled.  The other 90 hits (10 seeds × 9 duplicates) are skipped.
_UNIQUE_ARTISTS = 10
_GENRE_SEEDS_COUNT = 10
_ARTISTS_SKIPPED = _UNIQUE_ARTISTS * (_GENRE_SEEDS_COUNT - 1)  # 90

# artist_albums() returns 2 albums per artist.
_ALBUMS_PER_ARTIST = 2
_TOTAL_ALBUMS = _UNIQUE_ARTISTS * _ALBUMS_PER_ARTIST  # 20

# album_tracks() returns 3 tracks per album.
_TRACKS_PER_ALBUM = 3
_TOTAL_TRACKS = _TOTAL_ALBUMS * _TRACKS_PER_ALBUM  # 60


@override_settings(SPOTIFY_USE_STUB_DATA=True)
class CrawlCatalogTests(TestCase):

    # --- full crawl ------------------------------------------------------------

    def test_full_crawl_creates_expected_counts(self):
        result = crawl_catalog()

        self.assertEqual(result.artists_created, _UNIQUE_ARTISTS)
        self.assertEqual(result.albums_created, _TOTAL_ALBUMS)
        self.assertEqual(result.tracks_created, _TOTAL_TRACKS)
        self.assertEqual(result.artists_skipped, _ARTISTS_SKIPPED)
        self.assertEqual(result.failed_artist_ids, [])
        self.assertIsNotNone(result.crawled_at)

    def test_full_crawl_populates_db(self):
        crawl_catalog()

        self.assertEqual(Artist.objects.count(), _UNIQUE_ARTISTS)
        self.assertEqual(Album.objects.count(), _TOTAL_ALBUMS)
        self.assertEqual(Track.objects.count(), _TOTAL_TRACKS)

    def test_albums_linked_to_artists(self):
        crawl_catalog()

        for artist in Artist.objects.all():
            self.assertEqual(
                artist.albums.count(), _ALBUMS_PER_ARTIST,
                f"Artist {artist.name} ({artist.spotify_id}) should have {_ALBUMS_PER_ARTIST} albums",
            )

    def test_tracks_linked_to_albums(self):
        crawl_catalog()

        for album in Album.objects.all():
            self.assertEqual(
                album.tracks.count(), _TRACKS_PER_ALBUM,
                f"Album {album.name} ({album.spotify_id}) should have {_TRACKS_PER_ALBUM} tracks",
            )

    # --- idempotency / resume --------------------------------------------------

    def test_second_crawl_skips_everything(self):
        crawl_catalog()
        result2 = crawl_catalog()

        # Nothing new created.
        self.assertEqual(result2.artists_created, 0)
        self.assertEqual(result2.albums_created, 0)
        self.assertEqual(result2.tracks_created, 0)

        # Every album and track is skipped; no Spotify fetches or DB writes
        # happen for already-persisted subtrees.
        self.assertEqual(result2.albums_skipped, _TOTAL_ALBUMS)
        # Tracks are never even reached (album skip returns early), so
        # tracks_skipped stays 0.
        self.assertEqual(result2.tracks_skipped, 0)

        # DB counts unchanged.
        self.assertEqual(Artist.objects.count(), _UNIQUE_ARTISTS)
        self.assertEqual(Album.objects.count(), _TOTAL_ALBUMS)
        self.assertEqual(Track.objects.count(), _TOTAL_TRACKS)

    def test_partial_crawl_resumes_correctly(self):
        """Pre-populate one artist's full subtree; crawl should skip that
        artist's albums entirely and still create the rest."""
        # Full crawl, then tear down artists 1-9 to simulate a partial run.
        crawl_catalog()
        # Delete tracks first (album FK is PROTECT), then albums, then artists.
        Track.objects.exclude(album__spotify_id__startswith='stub-artist-0').delete()
        Album.objects.exclude(spotify_id__startswith='stub-artist-0').delete()
        Artist.objects.exclude(spotify_id='stub-artist-0').delete()

        result = crawl_catalog()

        # Artist 0 already existed → not counted as created.  9 new artists.
        self.assertEqual(result.artists_created, 9)
        # Artist 0's 2 albums already existed → skipped entirely (no track
        # fetch or save for them).  9 × 2 = 18 new albums.
        self.assertEqual(result.albums_created, 18)
        self.assertEqual(result.albums_skipped, 2)
        # Because album skip returns early, artist 0's tracks are never visited.
        # 9 × 2 × 3 = 54 new tracks; 0 tracks skipped.
        self.assertEqual(result.tracks_created, 54)
        self.assertEqual(result.tracks_skipped, 0)

        # Final DB state is complete.
        self.assertEqual(Artist.objects.count(), _UNIQUE_ARTISTS)
        self.assertEqual(Album.objects.count(), _TOTAL_ALBUMS)
        self.assertEqual(Track.objects.count(), _TOTAL_TRACKS)

    def test_album_without_tracks_is_not_skipped(self):
        """An album created by the on-demand HTTP path has no tracks.  The
        crawl must still fetch and persist its tracks rather than skipping."""
        crawl_catalog()

        # Delete all tracks for artist 0's first album only.  The album row
        # itself stays — simulating what the on-demand search path produces.
        target_album_id = 'stub-artist-0-album-0'
        Track.objects.filter(album__spotify_id=target_album_id).delete()
        self.assertEqual(
            Track.objects.filter(album__spotify_id=target_album_id).count(), 0,
        )

        result = crawl_catalog()

        # That album should have been re-crawled (not skipped).
        # 1 album re-crawled × 3 tracks = 3 tracks created.  All other albums
        # already had tracks → skipped.
        self.assertEqual(result.albums_skipped, _TOTAL_ALBUMS - 1)
        self.assertEqual(result.tracks_created, _TRACKS_PER_ALBUM)
        # The album's tracks are back.
        self.assertEqual(
            Track.objects.filter(album__spotify_id=target_album_id).count(),
            _TRACKS_PER_ALBUM,
        )

    # --- failure handling ------------------------------------------------------

    @mock.patch('catalog.services.catalog_crawl._fetch_artist_albums')
    def test_per_artist_failure_continues_crawl(self, mock_albums):
        """If fetching albums for one artist raises, the crawl continues and
        records the failure."""
        call_count = {'n': 0}

        def fail_first(artist_id):
            call_count['n'] += 1
            if call_count['n'] == 1:
                raise Exception('Spotify 429')
            from catalog import spotify_stub
            return list(spotify_stub.artist_albums(artist_id).get('items', []))

        mock_albums.side_effect = fail_first
        result = crawl_catalog()

        # One artist's album fetch failed; the artist itself was already
        # persisted before the fetch, so all 10 artists are created.
        self.assertEqual(len(result.failed_artist_ids), 1)
        self.assertEqual(result.artists_created, _UNIQUE_ARTISTS)
        # 9 successful artists × 2 albums × 3 tracks = 54 tracks created.
        self.assertEqual(result.tracks_created, (_UNIQUE_ARTISTS - 1) * _ALBUMS_PER_ARTIST * _TRACKS_PER_ALBUM)
        # The failed artist has no albums or tracks in the DB.
        failed_id = result.failed_artist_ids[0]
        self.assertEqual(Album.objects.filter(artists__spotify_id=failed_id).count(), 0)

    @mock.patch('catalog.services.catalog_crawl._search_artists_by_genre')
    def test_genre_search_failure_continues(self, mock_search):
        """If one genre search raises, remaining seeds are still processed."""
        call_count = {'n': 0}

        def fail_first(genre_seed):
            call_count['n'] += 1
            if call_count['n'] == 1:
                raise Exception('network error')
            from catalog import spotify_stub
            return list(spotify_stub.search_response('artist').get('items', []))

        mock_search.side_effect = fail_first
        result = crawl_catalog()

        # First seed failed entirely; the other 9 seeds returned artists.
        # All 10 unique artists are still discovered via the remaining 9 seeds.
        self.assertEqual(result.artists_created, _UNIQUE_ARTISTS)
        self.assertEqual(Artist.objects.count(), _UNIQUE_ARTISTS)

    @mock.patch('catalog.services.catalog_crawl._fetch_album_tracks')
    def test_duplicate_track_number_does_not_abort_album(self, mock_tracks):
        """Spotify sometimes returns two tracks with the same track_number on
        an album (live versions, reissues).  The duplicate should be logged as
        a failed track, but the rest of the album and subsequent albums
        continue normally."""
        import copy
        from catalog import spotify_stub

        def tracks_with_duplicate(album_id):
            """Return 3 normal tracks plus a 4th that collides on track_number
            with track 0."""
            data = spotify_stub.album_tracks(album_id)
            items = list(data.get('items', []))
            # Clone track 0, change its spotify_id and name but keep track_number=1.
            collider = copy.deepcopy(items[0])
            collider['id'] = f"{album_id}-collider"
            collider['name'] = 'Collider Track'
            # track_number stays the same as items[0] → collision.
            items.append(collider)
            return items

        mock_tracks.side_effect = tracks_with_duplicate
        result = crawl_catalog()

        # Every album gets one colliding track → 20 albums × 1 = 20 failures.
        self.assertEqual(len(result.failed_track_ids), _TOTAL_ALBUMS)
        # The 3 normal tracks per album all succeed → 60 created.
        self.assertEqual(result.tracks_created, _TOTAL_TRACKS)
        # No artists failed — the collision did not propagate up.
        self.assertEqual(result.failed_artist_ids, [])
