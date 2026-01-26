from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from juke_auth.models import JukeUser

from tests.utils import REGISTRATION_VERIFY_RE


class TestRegistration(APITestCase):
    register_url = '/api/v1/auth/accounts/register/'
    verify_url = '/api/v1/auth/accounts/verify-registration/'
    resend_url = '/api/v1/auth/accounts/resend-registration/'

    def test_register_fail_missing_username(self):
        data = {'password': 'testpassword'}
        response = self.client.post(self.register_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.data)
        self.assertEqual(response.data['username'][0].code, 'required')

    def test_register_fail_missing_password(self):
        data = {'username': 'test'}
        response = self.client.post(self.register_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password', response.data)
        self.assertEqual(response.data['password_confirm'][0].code, 'required')

    def test_register_fail_missing_password_confirm(self):
        data = {'username': 'test', 'password': 'testpassword'}
        response = self.client.post(self.register_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password_confirm', response.data)
        self.assertEqual(response.data['password_confirm'][0].code, 'required')

    def test_register_fail_missing_email(self):
        data = {'username': 'test', 'password': 'testpassword', 'password_confirm': 'testpassword'}
        response = self.client.post(self.register_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)
        self.assertEqual(response.data['email'][0].code, 'required')

    def test_register_fail_passwords_do_not_match(self):
        data = {
            'username': 'test',
            'password': 'testpassword',
            'password_confirm': 'testpasswordo',
            'email': 'test@test.com',
        }
        response = self.client.post(self.register_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('password_confirm', response.data)
        self.assertEqual(response.data['password_confirm'][0].code, 'passwords-do-not-match')

    def test_register_fail_with_same_username(self):
        JukeUser.objects.create(username='test', password='testpassword', email='test@test.com')
        data = {
            'username': 'test',
            'password': 'testpassword',
            'password_confirm': 'testpassword',
            'email': 'test@test.com',
        }
        response = self.client.post(self.register_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('username', response.data)
        self.assertEqual(response.data['username'][0], 'A user with that username already exists.')

    def test_register_fail_with_same_email(self):
        JukeUser.objects.create(username='test1', password='testpassword', email='test@test.com')
        data = {
            'username': 'test2',
            'password': 'testpassword',
            'password_confirm': 'testpassword',
            'email': 'test@test.com',
        }
        response = self.client.post(self.register_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('email', response.data)
        self.assertEqual(response.data['email'][0].code, 'unique')

    def test_register_ok_check_email(self):
        from django.core.mail import outbox
        data = {
            'username': 'test',
            'password': 'testpassword',
            'password_confirm': 'testpassword',
            'email': 'test@test.com',
        }

        response = self.client.post(self.register_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertFalse(JukeUser.objects.get(username='test').is_active)
        self.assertIsNotNone(JukeUser.objects.get(username='test').auth_token)
        self.assertEqual(len(outbox), 1)
        self.assertEqual("Welcome to Juke! Please verify your Account", outbox[0].subject)
        self.assertIn("Welcome to Juke! Let's get listening.", outbox[0].body)

    @override_settings(DISABLE_REGISTRATION=True)
    def test_register_disabled(self):
        data = {
            'username': 'test',
            'password': 'testpassword',
            'password_confirm': 'testpassword',
            'email': 'test@test.com',
        }

        response = self.client.post(self.register_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)
        self.assertIn('detail', response.data)
        self.assertEqual(
            response.data['detail'],
            'Registration is temporarily disabled. Please try again later.',
        )

    def test_verify_fail_wrong_data(self):
        from django.core.mail import outbox

        data = {
            'username': 'test',
            'password': 'testpassword',
            'password_confirm': 'testpassword',
            'email': 'test@test.com',
        }

        # Registration call
        response = self.client.post(self.register_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(outbox), 1)

        # User should be inactive
        new_user = JukeUser.objects.get(username='test')
        self.assertFalse(new_user.is_active)

        # Now make a verify API call
        response = self.client.post(self.verify_url, {
            'user_id': new_user.id,
            'timestamp': 2000000,
            'signature': 'sdflsjdfkldsjfsd'
        }, format='json')

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("detail", response.data)
        self.assertEqual(response.data['detail'], "Invalid signature")

    def test_verify_ok(self):
        from django.core.mail import outbox

        data = {
            'username': 'test',
            'password': 'testpassword',
            'password_confirm': 'testpassword',
            'email': 'test@test.com',
        }

        # Registration call
        response = self.client.post(self.register_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(outbox), 1)

        # User should be inactive
        new_user = JukeUser.objects.get(username='test')
        self.assertFalse(new_user.is_active)
        self.assertIsNotNone(new_user.auth_token)

        # Extract verification data from email body (text or html)
        match = REGISTRATION_VERIFY_RE.search(outbox[0].body)
        if match is None and getattr(outbox[0], 'alternatives', None):
            for alt_body, mimetype in outbox[0].alternatives:
                if 'text/html' in mimetype:
                    match = REGISTRATION_VERIFY_RE.search(alt_body)
                    if match is not None:
                        break
        self.assertIsNotNone(match)
        verify_data = match.groupdict()
        self.assertEqual(int(verify_data['user_id']), new_user.id)

        # Now make a verify API call
        response = self.client.post(self.verify_url, verify_data, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('detail', response.data)
        self.assertEqual(response.data['detail'], "Account verified.")
        self.assertIn('token', response.data)
        self.assertEqual(response.data['username'], 'test')
        new_user.refresh_from_db()

        # Now user should be active
        self.assertTrue(new_user.is_active)

    def test_resend_registration_verification(self):
        from django.core.mail import outbox

        data = {
            'username': 'test',
            'password': 'testpassword',
            'password_confirm': 'testpassword',
            'email': 'test@test.com',
        }

        response = self.client.post(self.register_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(len(outbox), 1)

        response = self.client.post(self.resend_url, {'email': 'test@test.com'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(outbox), 2)

    def test_resend_registration_verification_missing_user(self):
        response = self.client.post(self.resend_url, {'email': 'missing@test.com'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'], 'No account found for that email or username.')

    def test_resend_registration_verification_active_user(self):
        data = {
            'username': 'test',
            'password': 'testpassword',
            'password_confirm': 'testpassword',
            'email': 'test@test.com',
        }

        response = self.client.post(self.register_url, data, format='json')
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        user = JukeUser.objects.get(username='test')
        user.is_active = True
        user.save(update_fields=['is_active'])

        response = self.client.post(self.resend_url, {'email': 'test@test.com'}, format='json')
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data['detail'], 'Account is already verified. Please sign in.')
