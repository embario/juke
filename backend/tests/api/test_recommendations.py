from unittest import mock
import uuid

import requests
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from juke_auth.models import JukeUser
from recommender.serializers import MLCoreIdentityItemSerializer


class RecommendationEndpointTests(APITestCase):
    url = '/api/v1/recommendations/'

    def setUp(self):
        self.user = JukeUser.objects.create_user(username='tester', password='secret', email='tester@example.com')

    def test_requires_authentication_returns_unauthorized(self):
        response = self.client.post(self.url, data={}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

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


class MLCoreRecommendationEndpointTests(APITestCase):
    url = '/api/v1/recommendations/mlcore/'
    spotify_id = '0VjIjW4GlUZAMYd2vXMi3b'
    excluded_mbid = 'cbf0e52b-d15d-4506-a951-fd753bd9234f'

    def setUp(self):
        self.user = JukeUser.objects.create_user(username='mlcore-tester', password='secret', email='mlcore@example.com')

    def test_requires_authentication_returns_unauthorized(self):
        response = self.client.post(self.url, data={}, format='json')
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_normalizes_musicbrainz_identifier_case(self):
        serializer = MLCoreIdentityItemSerializer(data={
            'source': 'musicbrainz',
            'resource_type': 'recording',
            'source_id': self.excluded_mbid.upper(),
        })

        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data['source_id'], self.excluded_mbid)

    @mock.patch('recommender.views.client.fetch_identity_recommendations')
    def test_posts_identity_payload_to_mlcore_ranker(self, mock_fetch):
        mock_fetch.return_value = {
            'items': [
                {
                    'canonical_item_id': '00000000-0000-0000-0000-000000000123',
                    'score': 1.25,
                    'components': {'pmi_sum': 1.25},
                },
            ],
            'ranker': 'cooccurrence',
            'seed_count': 1,
            'requested_seed_count': 1,
            'resolved_seed_count': 1,
            'unresolved_seed_items': [],
            'unresolved_exclude_items': [],
            'request_id': '00000000-0000-0000-0000-000000000999',
            'versions': {
                'api_version': 'v1',
                'model_version': 'v1.0.0',
                'training_run_id': None,
                'training_version': 'training-hash',
                'identity_graph_run_id': None,
                'identity_graph_version': 'identity-v1',
                'identity_graph_algorithm_version': 'canonical-alias-v2',
            },
            'generated_at': '2026-06-08T00:00:00Z',
        }
        payload = {
            'ranker': 'cooccurrence',
            'seed_items': [
                {'source': 'spotify', 'resource_type': 'track', 'source_id': self.spotify_id},
            ],
            'exclude_items': [
                {'source': 'musicbrainz', 'resource_type': 'recording', 'source_id': self.excluded_mbid},
            ],
            'limit': 15,
        }

        self.client.force_login(self.user)
        response = self.client.post(self.url, data=payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            response.data['items'][0]['canonical_item_id'],
            '00000000-0000-0000-0000-000000000123',
        )
        self.assertEqual(response.data['resolved_seed_count'], 1)
        self.assertEqual(response.data['versions']['identity_graph_version'], 'identity-v1')
        ranker, engine_payload = mock_fetch.call_args.args
        self.assertEqual(ranker, 'cooccurrence')
        self.assertEqual(engine_payload['seed_items'], payload['seed_items'])
        self.assertEqual(engine_payload['exclude_items'], payload['exclude_items'])
        self.assertEqual(engine_payload['limit'], 15)
        self.assertIsNotNone(uuid.UUID(engine_payload['request_id']))

    @mock.patch('recommender.views.client.fetch_identity_recommendations')
    def test_returns_unavailable_when_mlcore_call_fails(self, mock_fetch):
        mock_fetch.side_effect = requests.Timeout('engine timed out')

        self.client.force_login(self.user)
        response = self.client.post(
            self.url,
            data={
                'seed_items': [
                    {'source': 'spotify', 'resource_type': 'track', 'source_id': self.spotify_id},
                ],
            },
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertEqual(response.data['detail'], 'recommendations unavailable')

    @mock.patch('recommender.views.client.fetch_identity_recommendations')
    def test_returns_bad_gateway_for_invalid_mlcore_response(self, mock_fetch):
        mock_fetch.return_value = {'items': [{'canonical_item_id': 'not-a-uuid'}]}
        self.client.force_login(self.user)

        response = self.client.post(
            self.url,
            data={'seed_items': [{'source': 'spotify', 'resource_type': 'track', 'source_id': self.spotify_id}]},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_502_BAD_GATEWAY)
        self.assertEqual(response.data['detail'], 'recommendations unavailable')

    @mock.patch('recommender.views.client.fetch_identity_recommendations')
    def test_normalizes_and_deduplicates_spotify_identity_forms(self, mock_fetch):
        request_id = uuid.uuid4()
        mock_fetch.return_value = {
            'items': [],
            'ranker': 'cooccurrence',
            'seed_count': 1,
            'requested_seed_count': 1,
            'resolved_seed_count': 1,
            'unresolved_seed_items': [],
            'unresolved_exclude_items': [],
            'request_id': str(request_id),
            'versions': {
                'api_version': 'v1', 'model_version': 'v1', 'training_run_id': None,
                'training_version': '', 'identity_graph_run_id': None, 'identity_graph_version': '',
                'identity_graph_algorithm_version': 'canonical-alias-v2',
            },
            'generated_at': '2026-06-08T00:00:00Z',
        }
        self.client.force_login(self.user)

        response = self.client.post(
            self.url,
            data={'seed_items': [
                {'source': 'spotify', 'resource_type': 'track', 'source_id': f'spotify:track:{self.spotify_id}'},
                {'source': 'spotify', 'resource_type': 'track', 'source_id': f'https://open.spotify.com/track/{self.spotify_id}?si=test'},
            ]},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        engine_payload = mock_fetch.call_args.args[1]
        self.assertEqual(engine_payload['seed_items'], [
            {'source': 'spotify', 'resource_type': 'track', 'source_id': self.spotify_id},
        ])

    @mock.patch('recommender.views.client.fetch_identity_recommendations')
    def test_rejects_more_than_one_hundred_seeds_or_exclusions(self, mock_fetch):
        self.client.force_login(self.user)
        unique_spotify_ids = [f'{index:022d}' for index in range(101)]

        seed_response = self.client.post(
            self.url,
            data={'seed_items': [
                {'source': 'spotify', 'resource_type': 'track', 'source_id': source_id}
                for source_id in unique_spotify_ids
            ]},
            format='json',
        )
        exclusion_response = self.client.post(
            self.url,
            data={
                'seed_items': [{'source': 'spotify', 'resource_type': 'track', 'source_id': self.spotify_id}],
                'exclude_items': [
                    {'source': 'spotify', 'resource_type': 'track', 'source_id': source_id}
                    for source_id in unique_spotify_ids
                ],
            },
            format='json',
        )

        self.assertEqual(seed_response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(exclusion_response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_fetch.assert_not_called()

    @mock.patch('recommender.views.client.fetch_identity_recommendations')
    def test_validates_identity_seed_items(self, mock_fetch):
        self.client.force_login(self.user)
        response = self.client.post(
            self.url,
            data={'seed_items': [{'source': 'juke_catalog', 'resource_type': 'track', 'source_id': 'local-id'}]},
            format='json',
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        mock_fetch.assert_not_called()
