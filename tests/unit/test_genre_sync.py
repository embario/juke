from django.test import TestCase

from catalog.models import Genre
from catalog.services.genre_sync import sync_spotify_genres
from tests.utils import create_genre


class GenreSyncServiceTests(TestCase):
    def test_sync_creates_unique_genres(self):
        result = sync_spotify_genres(names=['Dream Pop', 'Noise Pop', 'Noise Pop'])

        self.assertEqual(result.created, 2)
        self.assertEqual(result.updated, 0)
        self.assertEqual(result.total, 2)
        self.assertEqual(Genre.objects.count(), 2)
        self.assertTrue(all(genre.spotify_id.startswith('genre:') for genre in Genre.objects.all()))

    def test_sync_updates_existing_entries(self):
        existing = create_genre(name='Dream Pop', spotify_id='legacy-id-123')

        result = sync_spotify_genres(names=['Dream Pop'])

        existing.refresh_from_db()
        self.assertEqual(result.created, 0)
        self.assertEqual(result.updated, 1)
        self.assertNotEqual(existing.spotify_id, 'legacy-id-123')
        self.assertIn('last_genre_sync', existing.custom_data)
        self.assertEqual(existing.name, 'Dream Pop')
