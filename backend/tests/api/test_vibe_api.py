import base64
import hashlib
import uuid
from datetime import timedelta
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from vibe.models import VibeAccountCapability, VibeAuthorizationCode, VibeEncryptedChange
from juke_auth.models import JukeUser, MusicProfile


def base64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')


class VibeAPITests(APITestCase):
    def setUp(self):
        self.user = JukeUser.objects.create_user(
            username='listener',
            email='listener@example.com',
            password='pass1234',
        )
        MusicProfile.objects.create(user=self.user, display_name='Quiet Listener')
        self.token = Token.objects.get(user=self.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {self.token.key}')

    def issue_code(self):
        verifier = 'v' * 43
        challenge = base64url(hashlib.sha256(verifier.encode('ascii')).digest())
        response = self.client.post(
            '/api/v1/auth/vibe/authorize',
            {
                'client_id': 'juke-vibe-mac',
                'redirect_uri': 'juke-vibe://auth/callback',
                'state': 'state-value',
                'code_challenge': challenge,
                'code_challenge_method': 'S256',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        query = parse_qs(urlparse(response.data['redirect_to']).query)
        return query['code'][0], verifier, query

    def test_authorize_exchange_is_pkce_bound_one_time_and_matches_swift_session(self):
        VibeAccountCapability.objects.create(user=self.user, cloud_ai_enabled=True)
        code, verifier, query = self.issue_code()
        self.assertEqual(query['state'], ['state-value'])
        self.assertNotIn(code, VibeAuthorizationCode.objects.values_list('code_digest', flat=True))

        self.client.credentials()
        payload = {
            'code': code,
            'code_verifier': verifier,
            'redirect_uri': 'juke-vibe://auth/callback',
        }
        response = self.client.post('/api/v1/auth/vibe/exchange', payload, format='json')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['account']['id'], str(self.user.pk))
        self.assertEqual(response.data['account']['displayName'], 'Quiet Listener')
        self.assertTrue(response.data['account']['cloudAIEnabled'])
        self.assertEqual(response.data['accessToken'], self.token.key)
        self.assertIsInstance(response.data['authenticatedAt'], float)

        replay = self.client.post('/api/v1/auth/vibe/exchange', payload, format='json')
        self.assertEqual(replay.status_code, status.HTTP_400_BAD_REQUEST)

    def test_exchange_rejects_wrong_verifier_without_consuming_code(self):
        code, verifier, _ = self.issue_code()
        self.client.credentials()
        wrong = self.client.post(
            '/api/v1/auth/vibe/exchange',
            {'code': code, 'code_verifier': 'x' * 43, 'redirect_uri': 'juke-vibe://auth/callback'},
            format='json',
        )
        self.assertEqual(wrong.status_code, status.HTTP_400_BAD_REQUEST)
        accepted = self.client.post(
            '/api/v1/auth/vibe/exchange',
            {'code': code, 'code_verifier': verifier, 'redirect_uri': 'juke-vibe://auth/callback'},
            format='json',
        )
        self.assertEqual(accepted.status_code, status.HTTP_200_OK)

    def test_exchange_rejects_expired_code(self):
        code, verifier, _ = self.issue_code()
        VibeAuthorizationCode.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.client.credentials()
        response = self.client.post(
            '/api/v1/auth/vibe/exchange',
            {'code': code, 'code_verifier': verifier, 'redirect_uri': 'juke-vibe://auth/callback'},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_authorize_rejects_unlisted_redirect(self):
        response = self.client.post(
            '/api/v1/auth/vibe/authorize',
            {
                'client_id': 'juke-vibe-mac',
                'redirect_uri': 'evil://callback',
                'state': 'state-value',
                'code_challenge': 'x' * 43,
                'code_challenge_method': 'S256',
            },
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def envelope(self, *, record_id=None, account_id=None, ciphertext=b'encrypted bytes', modified_at=800000000.0):
        return {
            'recordID': str(record_id or uuid.uuid4()),
            'accountID': account_id or str(self.user.pk),
            'kind': 'chatMessage',
            'ciphertext': base64.b64encode(ciphertext).decode('ascii'),
            'modifiedAt': modified_at,
            'encryptionVersion': 1,
        }

    def test_encrypted_put_is_idempotent_and_change_feed_round_trips_swift_shape(self):
        payload = self.envelope()
        url = f"/api/v1/vibe/encrypted-chat-records/{payload['recordID']}"
        first = self.client.put(url, payload, format='json')
        second = self.client.put(url, payload, format='json')
        self.assertEqual(first.status_code, status.HTTP_201_CREATED)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(VibeEncryptedChange.objects.count(), 1)

        changes = self.client.get('/api/v1/vibe/encrypted-chat-records')
        self.assertEqual(changes.status_code, status.HTTP_200_OK)
        self.assertEqual(changes.data['envelopes'], [payload])
        cursor = changes.data['cursor']
        empty = self.client.get('/api/v1/vibe/encrypted-chat-records', {'cursor': cursor})
        self.assertEqual(empty.data, {'envelopes': [], 'cursor': cursor})

        payload['ciphertext'] = base64.b64encode(b'new encrypted bytes').decode('ascii')
        payload['modifiedAt'] += 5
        updated = self.client.put(url, payload, format='json')
        self.assertEqual(updated.status_code, status.HTTP_201_CREATED)
        latest = self.client.get('/api/v1/vibe/encrypted-chat-records', {'cursor': cursor})
        self.assertEqual(latest.data['envelopes'], [payload])

    def test_encrypted_records_are_isolated_by_account(self):
        other = JukeUser.objects.create_user(username='other', email='other@example.com', password='pass1234')
        payload = self.envelope(account_id=str(other.pk))
        denied = self.client.put(
            f"/api/v1/vibe/encrypted-chat-records/{payload['recordID']}",
            payload,
            format='json',
        )
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)

        other_token = Token.objects.get(user=other)
        self.client.credentials(HTTP_AUTHORIZATION=f'Token {other_token.key}')
        feed = self.client.get('/api/v1/vibe/encrypted-chat-records')
        self.assertEqual(feed.data['envelopes'], [])

    def test_encrypted_put_rejects_stale_or_ambiguous_overwrite(self):
        payload = self.envelope(modified_at=800000100.0)
        url = f"/api/v1/vibe/encrypted-chat-records/{payload['recordID']}"
        self.assertEqual(self.client.put(url, payload, format='json').status_code, status.HTTP_201_CREATED)
        payload['ciphertext'] = base64.b64encode(b'different ciphertext').decode('ascii')
        same_time = self.client.put(url, payload, format='json')
        self.assertEqual(same_time.status_code, status.HTTP_409_CONFLICT)
        payload['modifiedAt'] -= 1
        stale = self.client.put(url, payload, format='json')
        self.assertEqual(stale.status_code, status.HTTP_409_CONFLICT)

    def test_encrypted_endpoint_rejects_plaintext_or_unknown_fields(self):
        payload = self.envelope()
        payload['body'] = 'private prose must not be accepted'
        response = self.client.put(
            f"/api/v1/vibe/encrypted-chat-records/{payload['recordID']}",
            payload,
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn('body', response.data)

    def test_metadata_prompt_rejects_private_prose(self):
        accepted = self.client.post(
            '/api/v1/vibe/opening-question',
            {'recentlyHeardMusic': ['Song — Artist'], 'currentTrack': None},
            format='json',
        )
        self.assertEqual(accepted.status_code, status.HTTP_200_OK)
        rejected = self.client.post(
            '/api/v1/vibe/opening-question',
            {'recentlyHeardMusic': [], 'currentTrack': None, 'chatHistory': ['secret']},
            format='json',
        )
        self.assertEqual(rejected.status_code, status.HTTP_400_BAD_REQUEST)

    def test_vibe_routes_accept_mac_bearer_token(self):
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {self.token.key}')
        response = self.client.post(
            '/api/v1/vibe/opening-question',
            {'recentlyHeardMusic': [], 'currentTrack': None},
            format='json',
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    @patch('vibe.views.generate_chat_response', return_value='A thoughtful reply.')
    def test_chat_requires_capability_and_does_not_persist_text(self, generate):
        denied = self.client.post('/api/v1/vibe/chat', {'message': 'I love this bridge.'}, format='json')
        self.assertEqual(denied.status_code, status.HTTP_403_FORBIDDEN)
        VibeAccountCapability.objects.update(cloud_ai_enabled=True)
        accepted = self.client.post(
            '/api/v1/vibe/chat',
            {'message': 'I love this bridge.', 'currentTrack': 'Song — Artist'},
            format='json',
        )
        self.assertEqual(accepted.status_code, status.HTTP_200_OK)
        self.assertEqual(accepted.data['reply'], 'A thoughtful reply.')
        generate.assert_called_once_with(message='I love this bridge.', current_track='Song — Artist')

    def test_health_is_public(self):
        self.client.credentials()
        response = self.client.get('/api/v1/health')
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data, {'status': 'ok'})
