"""
TuneTrivia services for track selection and trivia generation.
"""
import os
import random
from typing import Optional

from django.conf import settings

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials


class TrackSelectionService:
    """Service for selecting tracks for TuneTrivia games."""

    def __init__(self):
        self.use_stub = getattr(settings, 'SPOTIFY_USE_STUB_DATA', False)
        if not self.use_stub:
            # Get credentials from Django settings
            client_id = getattr(settings, 'SOCIAL_AUTH_SPOTIFY_KEY', None)
            client_secret = getattr(settings, 'SOCIAL_AUTH_SPOTIFY_SECRET', None)

            if client_id and client_secret:
                self.client = spotipy.Spotify(
                    client_credentials_manager=SpotifyClientCredentials(
                        client_id=client_id,
                        client_secret=client_secret
                    )
                )
            else:
                print("Warning: Spotify credentials not configured")
                self.client = None
                self.use_stub = True
        else:
            self.client = None

    def search_tracks(self, query: str, limit: int = 20) -> list[dict]:
        """
        Search for tracks by query string.
        Returns list of track info dicts with preview URLs.
        """
        if self.use_stub:
            return self._get_stub_tracks(limit)

        try:
            response = self.client.search(
                q=query,
                type='track',
                limit=limit
            )
            tracks = response.get('tracks', {}).get('items', [])
            # Return all tracks - preview URLs may not always be available
            return [self._format_track(track) for track in tracks]
        except Exception as e:
            print(f"Spotify search error: {e}")
            return []

    def get_random_tracks(
        self,
        count: int = 10,
        decade: Optional[str] = None,
        genre: Optional[str] = None,
        artist: Optional[str] = None,
    ) -> list[dict]:
        """
        Get random tracks based on filters.
        Only returns tracks with preview URLs.
        """
        if self.use_stub:
            return self._get_stub_tracks(count)

        tracks = []

        # Build search queries based on filters
        queries = self._build_search_queries(decade, genre, artist)

        for query in queries:
            if len(tracks) >= count:
                break

            try:
                # Search with random offset for variety
                offset = random.randint(0, 100)
                response = self.client.search(
                    q=query,
                    type='track',
                    limit=50,
                    offset=offset
                )
                results = response.get('tracks', {}).get('items', [])

                # Shuffle tracks for variety
                random.shuffle(results)
                for track in results:
                    if len(tracks) >= count:
                        break
                    # Avoid duplicates
                    track_id = track.get('id')
                    if not any(t['spotify_id'] == track_id for t in tracks):
                        tracks.append(self._format_track(track))

            except Exception as e:
                print(f"Spotify random tracks error: {e}")
                continue

        return tracks[:count]

    def get_track_by_id(self, spotify_id: str) -> Optional[dict]:
        """Get a single track by Spotify ID."""
        if self.use_stub:
            return self._get_stub_track(spotify_id)

        try:
            track = self.client.track(spotify_id)
            if track:
                return self._format_track(track)
            return None
        except Exception as e:
            print(f"Spotify get track error: {e}")
            return None

    def _build_search_queries(
        self,
        decade: Optional[str] = None,
        genre: Optional[str] = None,
        artist: Optional[str] = None,
    ) -> list[str]:
        """Build search queries based on filters."""
        queries = []

        # If artist specified, search for their tracks
        if artist:
            queries.append(f'artist:{artist}')

        # If genre specified, search popular tracks in that genre
        if genre:
            queries.append(f'genre:{genre}')

        # Decade-based searches using year ranges
        if decade:
            decade_queries = {
                '1960s': 'year:1960-1969',
                '1970s': 'year:1970-1979',
                '1980s': 'year:1980-1989',
                '1990s': 'year:1990-1999',
                '2000s': 'year:2000-2009',
                '2010s': 'year:2010-2019',
                '2020s': 'year:2020-2029',
            }
            if decade in decade_queries:
                queries.append(decade_queries[decade])

        # If no filters, use popular search terms
        if not queries:
            popular_terms = [
                'top hits', 'classic rock', 'pop hits', '90s hits',
                '80s classics', 'dance hits', 'r&b classics', 'hip hop hits',
                'country hits', 'alternative rock', 'indie pop', 'disco'
            ]
            queries = random.sample(popular_terms, min(3, len(popular_terms)))

        return queries

    def _format_track(self, track: dict) -> dict:
        """Format Spotify track data for TuneTrivia."""
        artists = track.get('artists', [])
        artist_name = artists[0].get('name', 'Unknown') if artists else 'Unknown'

        album = track.get('album', {})
        album_name = album.get('name', '')
        album_images = album.get('images', [])
        album_art_url = album_images[0].get('url', '') if album_images else ''

        return {
            'spotify_id': track.get('id', ''),
            'track_name': track.get('name', 'Unknown'),
            'artist_name': artist_name,
            'album_name': album_name,
            'album_art_url': album_art_url,
            'preview_url': track.get('preview_url', ''),
            'duration_ms': track.get('duration_ms', 0),
        }

    def _get_stub_tracks(self, count: int) -> list[dict]:
        """Return stub track data for testing."""
        stub_tracks = [
            {
                'spotify_id': 'stub1',
                'track_name': 'Bohemian Rhapsody',
                'artist_name': 'Queen',
                'album_name': 'A Night at the Opera',
                'album_art_url': '',
                'preview_url': 'https://example.com/preview1.mp3',
                'duration_ms': 354000,
            },
            {
                'spotify_id': 'stub2',
                'track_name': 'Billie Jean',
                'artist_name': 'Michael Jackson',
                'album_name': 'Thriller',
                'album_art_url': '',
                'preview_url': 'https://example.com/preview2.mp3',
                'duration_ms': 294000,
            },
            {
                'spotify_id': 'stub3',
                'track_name': 'Sweet Child O\' Mine',
                'artist_name': 'Guns N\' Roses',
                'album_name': 'Appetite for Destruction',
                'album_art_url': '',
                'preview_url': 'https://example.com/preview3.mp3',
                'duration_ms': 356000,
            },
        ]
        return stub_tracks[:count]

    def _get_stub_track(self, spotify_id: str) -> Optional[dict]:
        """Return a stub track for testing."""
        return {
            'spotify_id': spotify_id,
            'track_name': 'Test Track',
            'artist_name': 'Test Artist',
            'album_name': 'Test Album',
            'album_art_url': '',
            'preview_url': 'https://example.com/preview.mp3',
            'duration_ms': 300000,
        }


class TriviaGenerationService:
    """Service for generating trivia about tracks."""

    def generate_trivia(self, track_info: dict) -> Optional[str]:
        """
        Generate trivia for a track.
        For now, returns basic info. Can be enhanced with external APIs.
        """
        artist = track_info.get('artist_name', 'Unknown')
        album = track_info.get('album_name', '')

        if album:
            return f"This song appears on the album '{album}' by {artist}."

        return f"This song is performed by {artist}."
