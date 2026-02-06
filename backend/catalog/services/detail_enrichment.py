"""
Detail enrichment service for catalog resources.

This service enriches Genre, Artist, and Album resources with additional
data for detailed views in the frontend. It uses database-first caching
via the custom_data JSON field to minimize external API calls.
"""

import logging
import random

from django.conf import settings
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from catalog import spotify_stub
from catalog.models import Artist, Album, Track

logger = logging.getLogger(__name__)


def generate_lorem_ipsum(min_sentences=3, max_sentences=5):
    """
    Generate lorem ipsum placeholder text with specified number of sentences.

    Args:
        min_sentences: Minimum number of sentences
        max_sentences: Maximum number of sentences

    Returns:
        String with lorem ipsum text
    """
    sentences = [
        "Lorem ipsum dolor sit amet, consectetur adipiscing elit.",
        "Sed do eiusmod tempor incididunt ut labore et dolore magna aliqua.",
        "Ut enim ad minim veniam, quis nostrud exercitation ullamco laboris.",
        "Nisi ut aliquip ex ea commodo consequat.",
        "Duis aute irure dolor in reprehenderit in voluptate velit esse cillum dolore.",
        "Eu fugiat nulla pariatur excepteur sint occaecat cupidatat non proident.",
        "Sunt in culpa qui officia deserunt mollit anim id est laborum.",
        "Curabitur pretium tincidunt lacus nulla gravida orci a odio.",
        "Sed non mauris vitae erat consequat auctor eu in elit.",
        "Class aptent taciti sociosqu ad litora torquent per conubia nostra.",
    ]

    num_sentences = random.randint(min_sentences, max_sentences)
    selected = random.sample(sentences, num_sentences)
    return " ".join(selected)


class ResourceDetailService:
    """Service for enriching catalog resources with additional detail data."""

    @staticmethod
    def _normalize_spotify_id(raw_value):
        if not raw_value:
            return ''
        return str(raw_value)[:30]

    @staticmethod
    def _spotify_client():
        if getattr(settings, 'SPOTIFY_USE_STUB_DATA', False):
            return None
        return spotipy.Spotify(client_credentials_manager=SpotifyClientCredentials())

    @staticmethod
    def _fetch_album_track_items(album_spotify_id):
        if not album_spotify_id:
            return []

        if getattr(settings, 'SPOTIFY_USE_STUB_DATA', False):
            payload = spotify_stub.album_tracks(album_spotify_id)
            return payload.get('items', [])

        client = ResourceDetailService._spotify_client()
        if client is None:
            return []

        payload = client.album_tracks(album_spotify_id, limit=50)
        items = list(payload.get('items', []))
        while payload.get('next'):
            payload = client.next(payload)
            items.extend(payload.get('items', []))
        return items

    @staticmethod
    def _hydrate_album_tracks(album):
        if not album.spotify_id:
            return 0

        created_or_updated = 0
        try:
            track_items = ResourceDetailService._fetch_album_track_items(album.spotify_id)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Unable to hydrate tracks for album '%s': %s", album.name, exc)
            return 0

        for item in track_items:
            spotify_id = ResourceDetailService._normalize_spotify_id(item.get('id'))
            if not spotify_id:
                continue

            track, _ = Track.get_or_create_with_validated_data(
                album=album,
                data={
                    'id': spotify_id,
                    'name': item.get('name') or 'Unknown track',
                    'track_number': item.get('track_number') or 0,
                    'disc_number': item.get('disc_number') or 1,
                    'duration_ms': item.get('duration_ms') or 0,
                    'explicit': item.get('explicit') or False,
                },
            )
            track.spotify_data = {
                **(track.spotify_data or {}),
                'id': spotify_id,
                'type': 'track',
                'uri': item.get('uri') or f"spotify:track:{spotify_id}",
                'preview_url': item.get('preview_url') or '',
            }
            track.save(update_fields=['spotify_data'])
            created_or_updated += 1

        return created_or_updated

    @staticmethod
    def _fetch_artist_album_items(artist_spotify_id):
        if not artist_spotify_id:
            return []

        if getattr(settings, 'SPOTIFY_USE_STUB_DATA', False):
            payload = spotify_stub.artist_albums(artist_spotify_id, album_types='album,single')
            return payload.get('items', [])

        client = ResourceDetailService._spotify_client()
        if client is None:
            return []

        payload = client.artist_albums(artist_spotify_id, album_type='album,single', limit=50)
        items = list(payload.get('items', []))
        while payload.get('next'):
            payload = client.next(payload)
            items.extend(payload.get('items', []))
        return items

    @staticmethod
    def _hydrate_artist_albums(artist):
        if not artist.spotify_id:
            return 0

        created_or_updated = 0
        try:
            album_items = ResourceDetailService._fetch_artist_album_items(artist.spotify_id)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Unable to hydrate albums for artist '%s': %s", artist.name, exc)
            return 0

        for item in album_items:
            spotify_id = ResourceDetailService._normalize_spotify_id(item.get('id'))
            if not spotify_id:
                continue

            album, _ = Album.get_or_create_with_validated_data(
                data={
                    'id': spotify_id,
                    'name': item.get('name') or 'Unknown album',
                    'album_type': item.get('album_type') or 'album',
                    'total_tracks': item.get('total_tracks') or 0,
                    'release_date': item.get('release_date') or '1970-01-01',
                    'release_date_precision': item.get('release_date_precision') or 'day',
                },
            )
            album.spotify_data = {
                **(album.spotify_data or {}),
                'type': item.get('type') or 'album',
                'uri': item.get('uri') or f"spotify:album:{spotify_id}",
                'images': [entry.get('url') for entry in item.get('images', []) if isinstance(entry, dict) and entry.get('url')],
            }
            album.save(update_fields=['spotify_data'])
            album.artists.add(artist)
            created_or_updated += 1

        return created_or_updated

    @staticmethod
    def enrich_genre(genre):
        """
        Enrich a Genre with description and top 5 artists by popularity.

        Args:
            genre: Genre model instance

        Returns:
            Dict with:
                - description: Genre description (lorem ipsum placeholder)
                - top_artists: QuerySet of top 5 artists in this genre
        """
        custom_data = genre.custom_data or {}

        # Check if description exists in custom_data, otherwise generate
        if not custom_data.get('description'):
            custom_data['description'] = generate_lorem_ipsum(3, 5)
            genre.custom_data = custom_data
            genre.save()
            logger.info(f"Generated description for genre '{genre.name}'")

        # Get top 5 artists by Spotify popularity score
        # Filter artists that have this genre
        top_artists = Artist.objects.filter(
            genres=genre
        ).order_by('-spotify_data__popularity')[:5]

        logger.debug(f"Retrieved {top_artists.count()} top artists for genre '{genre.name}'")

        return {
            'description': custom_data.get('description', 'Description unavailable'),
            'top_artists': top_artists
        }

    @staticmethod
    def enrich_artist(artist):
        """
        Enrich an Artist with bio, albums, top tracks, and related artists.

        Args:
            artist: Artist model instance

        Returns:
            Dict with:
                - bio: Artist biography (lorem ipsum placeholder)
                - albums: QuerySet of artist's albums ordered by release date
                - top_tracks: List of top track IDs (if cached)
                - related_artists: List of related artist IDs (if cached)
        """
        custom_data = artist.custom_data or {}

        # Check if bio exists in custom_data, otherwise generate
        if not custom_data.get('bio'):
            custom_data['bio'] = generate_lorem_ipsum(3, 5)
            artist.custom_data = custom_data
            artist.save()
            logger.info(f"Generated bio for artist '{artist.name}'")

        # Get discography (albums) ordered by release date
        albums = Album.objects.filter(
            artists=artist
        ).order_by('-release_date')

        if not albums.exists():
            hydrated_albums = ResourceDetailService._hydrate_artist_albums(artist)
            if hydrated_albums:
                logger.info("Hydrated %s albums for artist '%s'", hydrated_albums, artist.name)
                albums = Album.objects.filter(
                    artists=artist
                ).order_by('-release_date')

        logger.debug(f"Retrieved {albums.count()} albums for artist '{artist.name}'")

        # Track list for playback and detail cards.
        top_tracks_ids = custom_data.get('top_tracks_ids', [])
        if top_tracks_ids:
            top_tracks = Track.objects.filter(
                spotify_id__in=top_tracks_ids
            )[:5]
        else:
            top_tracks = Track.objects.filter(
                album__artists=artist
            ).order_by('-album__release_date', 'track_number')[:5]

        if not top_tracks.exists():
            for album in albums[:5]:
                ResourceDetailService._hydrate_album_tracks(album)
            top_tracks = Track.objects.filter(
                album__artists=artist
            ).order_by('-album__release_date', 'track_number')[:5]

        # Related artists from cached Spotify ids, with same-genre fallback.
        related_artist_ids = custom_data.get('related_artist_ids', [])
        if related_artist_ids:
            related_artists = Artist.objects.filter(
                spotify_id__in=related_artist_ids
            )[:5]
        else:
            related_artists = Artist.objects.filter(
                genres__in=artist.genres.all()
            ).exclude(id=artist.id).distinct().order_by('-spotify_data__popularity')[:5]

        return {
            'bio': custom_data.get('bio', 'Description unavailable'),
            'albums': albums,
            'top_tracks': top_tracks,
            'top_tracks_ids': top_tracks_ids,
            'related_artists': related_artists,
            'related_artist_ids': related_artist_ids,
        }

    @staticmethod
    def enrich_album(album):
        """
        Enrich an Album with description, tracks, and related albums.

        Args:
            album: Album model instance

        Returns:
            Dict with:
                - description: Album description (lorem ipsum placeholder)
                - tracks: QuerySet of tracks ordered by track number
                - related_albums: QuerySet of related albums (placeholder logic)
        """
        custom_data = album.custom_data or {}

        # Check if description exists in custom_data, otherwise generate
        if not custom_data.get('description'):
            custom_data['description'] = generate_lorem_ipsum(3, 5)
            album.custom_data = custom_data
            album.save()
            logger.info(f"Generated description for album '{album.name}'")

        # Get tracks ordered by track number.
        tracks = Track.objects.filter(album=album).order_by('track_number')
        existing_count = tracks.count()
        expected_count = max(album.total_tracks or 0, 0)
        should_hydrate_tracks = existing_count == 0 or (expected_count > 0 and existing_count < expected_count)
        if should_hydrate_tracks:
            hydrated_count = ResourceDetailService._hydrate_album_tracks(album)
            if hydrated_count:
                logger.info(
                    "Hydrated %s tracks for album '%s' (%s -> %s expected)",
                    hydrated_count,
                    album.name,
                    existing_count,
                    expected_count,
                )
                tracks = Track.objects.filter(album=album).order_by('track_number')

        logger.debug(f"Retrieved {tracks.count()} tracks for album '{album.name}'")

        # Get related albums (TODO: integrate with recommender engine)
        # For now, use simple heuristic: albums by same artist or in same genre
        related_albums = Album.objects.none()  # Empty QuerySet for now

        # Try to get albums by same artists
        album_artists = album.artists.all()
        if album_artists.exists():
            related_albums = Album.objects.filter(
                artists__in=album_artists
            ).exclude(id=album.id).distinct()[:5]

            logger.debug(f"Retrieved {related_albums.count()} related albums for '{album.name}'")

        return {
            'description': custom_data.get('description', 'Description unavailable'),
            'tracks': tracks,
            'related_albums': related_albums,
        }
