from datetime import date
from unittest.mock import patch

from django.test import TestCase

from catalog.services.detail_enrichment import ResourceDetailService, generate_lorem_ipsum
from tests.utils import create_album, create_artist, create_genre, create_track


class DetailEnrichmentServiceTests(TestCase):
    def test_generate_lorem_ipsum_respects_sentence_bounds(self):
        text = generate_lorem_ipsum(3, 3)
        self.assertEqual(text.count('.'), 3)

    def test_enrich_genre_returns_top_five_artists_by_popularity(self):
        genre = create_genre(name='jazz')

        popularities = [12, 55, 98, 77, 33, 89]
        for idx, popularity in enumerate(popularities):
            artist = create_artist(name=f'artist-{idx}', spotify_data={'popularity': popularity})
            artist.genres.add(genre)

        enriched = ResourceDetailService.enrich_genre(genre)
        genre.refresh_from_db()

        self.assertIn('description', genre.custom_data)
        self.assertEqual(len(enriched['top_artists']), 5)
        self.assertEqual(enriched['top_artists'][0].spotify_data.get('popularity'), 98)

    def test_enrich_artist_returns_bio_discography_top_tracks_and_related_artists(self):
        genre = create_genre(name='fusion')
        artist = create_artist(name='Primary Artist')
        artist.genres.add(genre)

        related_artist = create_artist(name='Related Artist', spotify_id='related-artist-id')
        related_artist.genres.add(genre)

        album_old = create_album(name='Old Album', total_tracks=2, release_date=date(2000, 1, 1))
        album_new = create_album(name='New Album', total_tracks=2, release_date=date(2005, 1, 1))
        album_old.artists.add(artist)
        album_new.artists.add(artist)

        track_one = create_track(
            name='Track One',
            album=album_old,
            track_number=1,
            disc_number=1,
            duration_ms=120000,
            explicit=False,
            spotify_id='track-1',
        )
        track_two = create_track(
            name='Track Two',
            album=album_new,
            track_number=1,
            disc_number=1,
            duration_ms=180000,
            explicit=False,
            spotify_id='track-2',
        )

        artist.custom_data = {
            'top_tracks_ids': [track_one.spotify_id, track_two.spotify_id],
            'related_artist_ids': [related_artist.spotify_id],
        }
        artist.save(update_fields=['custom_data'])

        enriched = ResourceDetailService.enrich_artist(artist)
        artist.refresh_from_db()

        self.assertIn('bio', artist.custom_data)
        self.assertEqual([album.name for album in enriched['albums'][:2]], ['New Album', 'Old Album'])
        self.assertEqual({track.spotify_id for track in enriched['top_tracks']}, {'track-1', 'track-2'})
        self.assertEqual([entry.spotify_id for entry in enriched['related_artists']], ['related-artist-id'])

    def test_enrich_artist_hydrates_albums_when_discography_is_empty(self):
        artist = create_artist(name='Hydrate Artist', spotify_id='hydrate-artist-1')

        enriched = ResourceDetailService.enrich_artist(artist)

        self.assertGreaterEqual(enriched['albums'].count(), 1)

    def test_enrich_album_returns_tracks_in_order_and_related_albums(self):
        artist = create_artist(name='Album Artist')
        album = create_album(name='Main Album', total_tracks=2, release_date=date(2020, 2, 2))
        album.artists.add(artist)

        related = create_album(name='Sibling Album', total_tracks=1, release_date=date(2021, 1, 1))
        related.artists.add(artist)

        create_track(
            name='Track 2',
            album=album,
            track_number=2,
            disc_number=1,
            duration_ms=120000,
            explicit=False,
        )
        create_track(
            name='Track 1',
            album=album,
            track_number=1,
            disc_number=1,
            duration_ms=90000,
            explicit=False,
        )

        enriched = ResourceDetailService.enrich_album(album)
        album.refresh_from_db()

        self.assertIn('description', album.custom_data)
        self.assertEqual([track.track_number for track in enriched['tracks']], [1, 2])
        related_ids = {entry.id for entry in enriched['related_albums']}
        self.assertIn(related.id, related_ids)
        self.assertNotIn(album.id, related_ids)

    def test_enrich_album_hydrates_when_existing_tracks_are_partial(self):
        artist = create_artist(name='Partial Album Artist')
        album = create_album(name='Partial Album', total_tracks=3, release_date=date(2022, 2, 2), spotify_id='partial-album')
        album.artists.add(artist)
        create_track(
            name='Existing Track 1',
            album=album,
            track_number=1,
            disc_number=1,
            duration_ms=120000,
            explicit=False,
            spotify_id='partial-track-1',
        )

        def hydrate_stub(target_album):
            create_track(
                name='Hydrated Track 2',
                album=target_album,
                track_number=2,
                disc_number=1,
                duration_ms=130000,
                explicit=False,
                spotify_id='partial-track-2',
            )
            create_track(
                name='Hydrated Track 3',
                album=target_album,
                track_number=3,
                disc_number=1,
                duration_ms=140000,
                explicit=False,
                spotify_id='partial-track-3',
            )
            return 2

        with patch.object(ResourceDetailService, '_hydrate_album_tracks', side_effect=hydrate_stub) as hydrate_mock:
            enriched = ResourceDetailService.enrich_album(album)

        hydrate_mock.assert_called_once_with(album)
        self.assertEqual([track.track_number for track in enriched['tracks']], [1, 2, 3])
