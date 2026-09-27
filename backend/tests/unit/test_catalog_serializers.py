from django.test import TestCase

from catalog.models import Album, Artist, Genre, Track
from catalog.serializers import (
    AlbumDetailSerializer,
    ArtistDetailSerializer,
    SpotifyAlbumSerializer,
    SpotifyArtistSerializer,
    SpotifyTrackSerializer,
)


class SpotifyArtistSerializerTests(TestCase):
    def test_create_populates_genres_and_spotify_data(self):
        payload = {
            'id': 'artist-123',
            'type': 'artist',
            'uri': 'spotify:artist:artist-123',
            'name': 'Serializer Artist',
            'genres': ['psych rock', 'post-metal'],
            'popularity': 77,
            'followers': {'total': 4200},
            'images': [{'url': 'https://img.example/1.jpg'}],
        }

        serializer = SpotifyArtistSerializer(data=payload, context={'request': None})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        artist = serializer.save()

        self.assertEqual(artist.spotify_id, 'artist-123')
        self.assertEqual(artist.genres.count(), 2)
        self.assertEqual(Genre.objects.count(), 2)
        self.assertEqual(artist.spotify_data['followers'], 4200)
        self.assertEqual(artist.spotify_data['images'], ['https://img.example/1.jpg'])

    def test_second_create_updates_existing_artist(self):
        payload = {
            'id': 'artist-existing',
            'type': 'artist',
            'uri': 'spotify:artist:artist-existing',
            'name': 'Existing Artist',
            'genres': ['ambient'],
            'popularity': 50,
            'followers': {'total': 100},
            'images': [],
        }
        serializer = SpotifyArtistSerializer(data=payload, context={'request': None})
        serializer.is_valid(raise_exception=True)
        serializer.save()

        payload['name'] = 'Existing Artist (Renamed)'
        payload['popularity'] = 90
        payload['followers'] = {'total': 900}
        serializer = SpotifyArtistSerializer(data=payload, context={'request': None})
        serializer.is_valid(raise_exception=True)
        artist = serializer.save()

        self.assertEqual(Artist.objects.count(), 1)
        self.assertEqual(artist.name, 'Existing Artist (Renamed)')
        self.assertEqual(artist.spotify_data['popularity'], 90)
        self.assertEqual(artist.spotify_data['followers'], 900)


class SpotifyAlbumSerializerTests(TestCase):
    def test_create_links_artists_and_sets_spotify_data(self):
        payload = {
            'id': 'album-1',
            'type': 'album',
            'uri': 'spotify:album:album-1',
            'name': 'Serializer Album',
            'album_type': 'album',
            'total_tracks': 8,
            'release_date': '2001-05-15',
            'release_date_precision': 'day',
            'images': [{'url': 'https://img.example/album.jpg'}],
            'artists': [{'id': 'artist-a', 'name': 'Artist A'}],
        }

        serializer = SpotifyAlbumSerializer(data=payload, context={'request': None})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        album = serializer.save()

        self.assertEqual(album.spotify_id, 'album-1')
        self.assertEqual(album.artists.count(), 1)
        self.assertEqual(Artist.objects.count(), 1)
        self.assertEqual(album.spotify_data['images'], ['https://img.example/album.jpg'])
        self.assertEqual(album.album_type, 'ALBUM')


class SpotifyTrackSerializerTests(TestCase):
    def test_create_creates_album_and_track(self):
        track_payload = {
            'id': 'track-1',
            'type': 'track',
            'uri': 'spotify:track:track-1',
            'name': 'Serializer Track',
            'track_number': 1,
            'disc_number': 1,
            'duration_ms': 123456,
            'explicit': False,
            'album': {
                'id': 'album-track-1',
                'type': 'album',
                'uri': 'spotify:album:album-track-1',
                'name': 'Album For Track',
                'album_type': 'single',
                'total_tracks': 1,
                'release_date': '2020-08-01',
                'release_date_precision': 'day',
                'images': [{'url': 'https://img.example/track-album.jpg'}],
                'artists': [{'id': 'artist-track', 'name': 'Artist Track'}],
            },
        }

        serializer = SpotifyTrackSerializer(data=track_payload, context={'request': None})
        self.assertTrue(serializer.is_valid(), serializer.errors)
        track = serializer.save()

        self.assertEqual(track.spotify_id, 'track-1')
        self.assertEqual(track.album.spotify_id, 'album-track-1')
        self.assertEqual(Album.objects.count(), 1)
        self.assertEqual(Track.objects.count(), 1)
        self.assertEqual(track.spotify_data['uri'], 'spotify:track:track-1')
        self.assertEqual(track.album.spotify_data['images'], ['https://img.example/track-album.jpg'])
        self.assertEqual(list(track.album.artists.values_list('name', flat=True)), ['Artist Track'])
        self.assertEqual(serializer.data['artwork_url'], 'https://img.example/track-album.jpg')
        self.assertEqual(serializer.data['artist_names'], 'Artist Track')


class CatalogDetailIdentityTests(TestCase):
    def test_detail_and_nested_resources_expose_numeric_primary_keys(self):
        artist = Artist.objects.create(name='Detail Artist')
        related_artist = Artist.objects.create(name='Related Artist')
        album = Album.objects.create(name='Detail Album', total_tracks=1, release_date='2026-01-01')
        album.artists.add(artist)
        track = Track.objects.create(name='Detail Track', album=album, track_number=1, disc_number=1, duration_ms=180000, explicit=False)
        genre = Genre.objects.create(name='Detail Genre')
        artist.genres.add(genre)
        artist._enriched_albums = [album]
        artist._enriched_top_tracks = [track]
        artist._enriched_related_artists = [related_artist]
        album._enriched_tracks = [track]
        album._enriched_related_albums = [album]

        artist_data = ArtistDetailSerializer(artist, context={'request': None}).data
        self.assertEqual(artist_data['pk'], artist.pk)
        self.assertEqual(artist_data['albums'][0]['pk'], album.pk)
        self.assertEqual(artist_data['top_tracks'][0]['pk'], track.pk)
        self.assertEqual(artist_data['related_artists'][0]['pk'], related_artist.pk)
        self.assertEqual(artist_data['genres'][0]['pk'], genre.pk)
        album_data = AlbumDetailSerializer(album, context={'request': None}).data
        self.assertEqual(album_data['pk'], album.pk)
        self.assertEqual(album_data['tracks'][0]['pk'], track.pk)
        self.assertEqual(album_data['related_albums'][0]['pk'], album.pk)
