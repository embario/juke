"""
Detail enrichment service for catalog resources.

This service enriches Genre, Artist, and Album resources with additional
data for detailed views in the frontend. It uses database-first caching
via the custom_data JSON field to minimize external API calls.
"""

import logging
import random

from catalog.models import Genre, Artist, Album, Track

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
        # Check if description exists in custom_data, otherwise generate
        if not genre.custom_data.get('description'):
            genre.custom_data['description'] = generate_lorem_ipsum(3, 5)
            genre.save()
            logger.info(f"Generated description for genre '{genre.name}'")

        # Get top 5 artists by Spotify popularity score
        # Filter artists that have this genre
        top_artists = Artist.objects.filter(
            genres=genre
        ).order_by('-spotify_data__popularity')[:5]

        logger.debug(f"Retrieved {top_artists.count()} top artists for genre '{genre.name}'")

        return {
            'description': genre.custom_data.get('description', 'Description unavailable'),
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
        # Check if bio exists in custom_data, otherwise generate
        if not artist.custom_data.get('bio'):
            artist.custom_data['bio'] = generate_lorem_ipsum(3, 5)
            artist.save()
            logger.info(f"Generated bio for artist '{artist.name}'")

        # Get discography (albums) ordered by release date
        albums = Album.objects.filter(
            artists=artist
        ).order_by('-release_date')

        logger.debug(f"Retrieved {albums.count()} albums for artist '{artist.name}'")

        # Get top tracks IDs if cached (to be fetched from Spotify API separately)
        top_tracks_ids = artist.custom_data.get('top_tracks_ids', [])

        # Get related artists IDs if cached (to be fetched from Spotify API separately)
        related_artist_ids = artist.custom_data.get('related_artist_ids', [])

        return {
            'bio': artist.custom_data.get('bio', 'Description unavailable'),
            'albums': albums,
            'top_tracks_ids': top_tracks_ids,
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
        # Check if description exists in custom_data, otherwise generate
        if not album.custom_data.get('description'):
            album.custom_data['description'] = generate_lorem_ipsum(3, 5)
            album.save()
            logger.info(f"Generated description for album '{album.name}'")

        # Get tracks ordered by track number
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
            'description': album.custom_data.get('description', 'Description unavailable'),
            'tracks': tracks,
            'related_albums': related_albums,
        }
