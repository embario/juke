from django.test import SimpleTestCase

from catalog.utils import APIResponse


class APIResponseTests(SimpleTestCase):
    def test_multi_resource_payload_exposes_metadata(self):
        payload = {
            'href': 'https://stub/artists',
            'items': [
                {'id': 'artist-1', 'name': 'One'},
                {'id': 'artist-2', 'name': 'Two'},
            ],
            'limit': 2,
            'offset': 0,
            'total': 2,
            'previous': None,
        }

        response = APIResponse(payload)

        self.assertTrue(response.multi_resource)
        data = response.data
        self.assertEqual(data['count'], 2)
        self.assertEqual(len(data['results']), 2)
        self.assertEqual(list(response)[0]['id'], 'artist-1')

    def test_single_resource_payload_returns_first_item(self):
        payload = {
            'id': 'artist-99',
            'name': 'Solo Artist',
            'followers': 10,
        }

        response = APIResponse(payload)

        self.assertFalse(response.multi_resource)
        self.assertEqual(response.data['id'], 'artist-99')
        self.assertEqual(next(iter(response))['id'], 'artist-99')
