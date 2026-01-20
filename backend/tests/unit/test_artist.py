from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile

from catalog.models import Artist, ArtistImageResource
from tests.utils import create_genre, create_artist


class ArtistTests(TestCase):

    def test_create_ok(self):
        g1 = create_genre(name='some-genre')
        create_artist(name='some-artist')
        a2 = create_artist(name='some-artist', spotify_id='12345')
        a2.genres.add(g1)

        self.assertEqual(Artist.objects.count(), 2)
        self.assertEqual(a2.genres.count(), 1)

    def test_create_with_images(self):
        a1 = create_artist(name='some-artist')
        image1 = SimpleUploadedFile('file1.png', b'file_content', content_type='image/png')
        image2 = SimpleUploadedFile('file2.png', b'file_content', content_type='image/png')
        ArtistImageResource.objects.create(image=image1, artist=a1)
        ArtistImageResource.objects.create(image=image2, artist=a1)
        self.assertEqual(a1.images.count(), 2)
