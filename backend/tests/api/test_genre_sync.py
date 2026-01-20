from unittest import mock

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

    @mock.patch('catalog.views.sync_spotify_genres_task.delay')
    def test_admin_trigger_invokes_celery_task(self, mock_delay):
        mock_delay.return_value = mock.Mock(id='task-123')
        staff_user = JukeUser.objects.create_superuser(
            username='celery',
            password='pw',
            email='celery@example.com',
        )
        self.client.force_login(staff_user)

        response = self.client.post(self.sync_url)

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        mock_delay.assert_called_once_with()
        self.assertEqual(response.data['task_id'], 'task-123')
