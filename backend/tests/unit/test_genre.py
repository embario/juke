from django.test import TestCase
from django.db.utils import IntegrityError

from catalog.models import Genre

from tests.utils import create_genre


class GenreTests(TestCase):

    def test_create_fail(self):
        create_genre(name='test-genre')

        with self.assertRaises(IntegrityError):
            create_genre(name='test-genre')

    def test_create_ok(self):
        create_genre(name='test-genre')
        create_genre(name='test-genre-2', custom_data={'some custom data': 1})
        create_genre(name='test-genre-3', spotify_data={'some spotify data': True})
        self.assertEqual(Genre.objects.count(), 3)
