from rest_framework import status
from rest_framework.test import APITestCase

from juke_auth.models import JukeUser


class GenreSyncAPITests(APITestCase):
    sync_url = '/api/v1/genres/refresh/'

    def test_requires_admin_permissions(self):
        user = JukeUser.objects.create_user(username='listener', password='pw', email='listener@example.com')
        self.client.force_login(user)

        response = self.client.post(self.sync_url)

        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_trigger_sync_task(self):
        staff_user = JukeUser.objects.create_superuser(
            username='curator',
            password='pw',
            email='curator@example.com',
        )
        self.client.force_login(staff_user)

        response = self.client.post(self.sync_url)

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        self.assertIn('task_id', response.data)
        self.assertTrue(response.data['task_id'])
