from unittest import mock

from django.utils import timezone
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

    @mock.patch('recommender.views.client.fetch_recommendations')
    def test_limit_and_resource_types_forwarded(self, mock_fetch):
        mock_fetch.return_value = {
            'artists': [],
            'albums': [],
            'tracks': [],
            'model_version': 'v1-test',
            'generated_at': '2026-01-18T00:00:00Z',
        }

        self.client.force_login(self.user)
        payload = {
            'artists': ['Tool'],
            'resource_types': ['artists', 'tracks'],
            'limit': 25,
        }

        response = self.client.post(self.url, data=payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        forwarded = mock_fetch.call_args[0][0]
        self.assertEqual(forwarded['limit'], 25)
        self.assertEqual(forwarded['resource_types'], ['artists', 'tracks'])
        self.assertEqual(forwarded['artists'], ['Tool'])

    @mock.patch('recommender.views.timezone.now')
    @mock.patch('recommender.views.client.fetch_recommendations')
    def test_generated_at_defaults_when_missing(self, mock_fetch, mock_now):
        fixed = timezone.datetime(2026, 1, 19, 12, 0, tzinfo=timezone.UTC)
        mock_now.return_value = fixed
        mock_fetch.return_value = {
            'artists': [],
            'albums': [],
            'tracks': [],
            'model_version': 'v2',
        }

        self.client.force_login(self.user)
        response = self.client.post(self.url, data={'artists': ['Tool']}, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        expected = fixed.isoformat().replace('+00:00', 'Z')
        self.assertEqual(response.data['generated_at'], expected)
        self.assertEqual(response.data['model_version'], 'v2')
