from rest_framework import status
from rest_framework.test import APITestCase

from catalog.models import SearchHistory, SearchHistoryResource
from juke_auth.models import JukeUser


class SearchHistoryAPITests(APITestCase):
    endpoint = '/api/v1/search-history/'

    def setUp(self):
        self.user = JukeUser.objects.create_user(
            username='history-user',
            email='history@example.com',
            password='pass1234',
        )
        self.other_user = JukeUser.objects.create_user(
            username='other-user',
            email='other@example.com',
            password='pass1234',
        )
        self.client.force_login(self.user)

    def _payload(self, query='jazz'):
        return {
            'search_query': query,
            'engaged_resources': [
                {'resource_type': 'artist', 'resource_id': 1, 'resource_name': 'Miles Davis'},
                {'resource_type': 'album', 'resource_id': 2, 'resource_name': 'Kind of Blue'},
            ],
        }

    def test_create_search_history_requires_authentication(self):
        self.client.logout()

        response = self.client.post(self.endpoint, data=self._payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_create_search_history_persists_engaged_resources(self):
        response = self.client.post(self.endpoint, data=self._payload(), format='json')

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(SearchHistory.objects.count(), 1)
        self.assertEqual(SearchHistoryResource.objects.count(), 2)

        history = SearchHistory.objects.get()
        self.assertEqual(history.user, self.user)
        self.assertEqual(history.search_query, 'jazz')
        self.assertEqual(history.engaged_resources.count(), 2)

    def test_create_search_history_rejects_blank_query(self):
        response = self.client.post(self.endpoint, data=self._payload(query='   '), format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('search_query', response.data)
        self.assertEqual(SearchHistory.objects.count(), 0)

    def test_create_search_history_rejects_invalid_resource_type(self):
        payload = self._payload()
        payload['engaged_resources'][0]['resource_type'] = 'podcast'

        response = self.client.post(self.endpoint, data=payload, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('engaged_resources', response.data)
        self.assertEqual(SearchHistory.objects.count(), 0)

    def test_list_returns_only_authenticated_users_history(self):
        own_history = SearchHistory.objects.create(user=self.user, search_query='jazz')
        SearchHistoryResource.objects.create(
            search_history=own_history,
            resource_type='artist',
            resource_id=99,
            resource_name='Herbie Hancock',
        )
        SearchHistory.objects.create(user=self.other_user, search_query='metal')

        response = self.client.get(self.endpoint, format='json')

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['search_query'], 'jazz')
        self.assertEqual(len(response.data['results'][0]['engaged_resources']), 1)
