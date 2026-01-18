from unittest import mock

from rest_framework import status
from rest_framework.test import APITestCase

from juke_auth.models import JukeUser


class RecommendationEndpointTests(APITestCase):
    url = '/api/v1/recommendations/'

    def setUp(self):
        self.user = JukeUser.objects.create_user(username='tester', password='secret', email='tester@example.com')

    def test_requires_authentication(self):
        response = self.client.post(self.url, data={}, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    @mock.patch('recommender.views.client.fetch_recommendations')
    def test_returns_engine_payload(self, mock_fetch):
        mock_fetch.return_value = {
            'artists': [{'name': 'A Perfect Circle', 'likeness': 0.92}],
            'albums': [],
            'tracks': [],
            'model_version': 'v1-test',
            'generated_at': '2026-01-18T00:00:00Z',
        }

        self.client.force_login(self.user)
        payload = {'artists': ['Tool']}
        response = self.client.post(self.url, data=payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['artists'][0]['name'], 'A Perfect Circle')
        mock_fetch.assert_called_once()

    @mock.patch('recommender.views.client.fetch_recommendations')
    def test_validation_requires_seed(self, mock_fetch):
        self.client.force_login(self.user)
        response = self.client.post(self.url, data={'limit': 5}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_fetch.assert_not_called()
