from rest_framework import status
from rest_framework.test import APITestCase

from juke_auth.models import JukeUser


class TestUser(APITestCase):
    user_url = '/api/v1/users/'

    def test_get_fail_unauthenticated_forbidden(self):
        response = self.client.get(self.user_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get_authenticated_ok(self):
        self.client.force_login(JukeUser.objects.create(username='test', password='test'))
        response = self.client.get(self.user_url, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['count'], 1)
