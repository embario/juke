from unittest import mock

import requests
from django.test import SimpleTestCase

from recommender.services import client


class RecommenderClientTests(SimpleTestCase):
    @mock.patch('recommender.services.client.requests.post')
    def test_fetch_recommendations_posts_payload(self, mock_post):
        mock_response = mock.Mock()
        mock_response.json.return_value = {'artists': []}
        mock_response.raise_for_status.return_value = None
        mock_post.return_value = mock_response

        payload = {'artists': ['Tool']}
        with mock.patch('recommender.services.client.ENGINE_BASE_URL', 'http://engine.test/'):
            response = client.fetch_recommendations(payload)

        self.assertEqual(response, {'artists': []})
        mock_post.assert_called_once_with(
            'http://engine.test/recommend',
            json=payload,
            timeout=client.DEFAULT_TIMEOUT,
        )

    @mock.patch('recommender.services.client.requests.post')
    def test_fetch_recommendations_raises_for_http_errors(self, mock_post):
        mock_response = mock.Mock()
        mock_response.raise_for_status.side_effect = requests.HTTPError('boom')
        mock_post.return_value = mock_response

        with mock.patch('recommender.services.client.ENGINE_BASE_URL', 'http://engine.test'):
            with self.assertRaises(requests.HTTPError):
                client.fetch_recommendations({'artists': ['Tool']})

    @mock.patch('recommender.services.client._request')
    def test_build_vector_from_names_uses_text_embeddings(self, mock_request):
        mock_request.return_value = {'embedding': [0.1, 0.2]}

        result = client.build_vector_from_names(['Tool', 'Opeth'])

        self.assertEqual(result, {'embedding': [0.1, 0.2]})
        mock_request.assert_called_once_with(
            '/embed',
            {
                'resource_type': 'text',
                'attributes': {'tokens': ['Tool', 'Opeth']},
            },
        )
