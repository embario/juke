from datetime import date

from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile

from catalog.models import Album, Artist, AlbumImageResource
from tests.utils import create_genre, create_artist, create_album


class AlbumTests(TestCase):

    def test_create_ok(self):
        create_genre(name='some-genre')
        a1 = create_artist(name='some-artist')
        a2 = create_artist(name='some-artist-2')
        al1 = create_album(name='some-album-1', total_tracks=10, release_date=date(year=1970, month=1, day=10))
        al2 = create_album(name='some-album-2', total_tracks=1, release_date=date(year=1973, month=4, day=20))
        al3 = create_album(name='some-album-3', total_tracks=13, release_date=date(year=1976, month=7, day=15))

        al1.artists.add(a1)
        al2.artists.add(a1)
        al3.artists.add(a1)
        al3.artists.add(a2)

        self.assertEqual(Artist.objects.count(), 2)
        self.assertEqual(Album.objects.count(), 3)
        self.assertEqual(al1.artists.count(), 1)
        self.assertEqual(al2.artists.count(), 1)
        self.assertEqual(al3.artists.count(), 2)

    def test_create_with_images(self):
        al = create_album(name='some-album', total_tracks=10, release_date=date(year=1970, month=1, day=10))
        image1 = SimpleUploadedFile('file1.png', b'file_content', content_type='image/png')
        image2 = SimpleUploadedFile('file2.png', b'file_content', content_type='image/png')
        AlbumImageResource.objects.create(image=image1, album=al)
        AlbumImageResource.objects.create(image=image2, album=al)
        self.assertEqual(al.images.count(), 2)

    def test_get_or_create_normalizes_release_date_precision(self):
        data = {
            'name': 'Precision Test',
            'id': 'album-precision-test',
            'album_type': 'album',
            'total_tracks': 10,
            'release_date': '2006',
        }

        album, created = Album.get_or_create_with_validated_data(data=data)
        self.assertTrue(created)
        self.assertEqual(album.release_date, date(2006, 1, 1))

        data['release_date'] = '2006-05'
        data['release_date_precision'] = 'month'

        album, created = Album.get_or_create_with_validated_data(data=data)
        self.assertFalse(created)
        self.assertEqual(album.release_date, date(2006, 5, 1))
