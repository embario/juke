import uuid
from unittest.mock import Mock, patch

import requests

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework.authtoken.models import Token
from rest_framework.test import APITestCase

from vibe.memory_models import MemoryMedia, MusicMemory
from vibe.memory_services import classify_memory, memory_recommendation_context


@override_settings(JEV_CLASSIFICATION_URL='')
class MusicMemoryTests(APITestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username='memory-owner', email='memory@example.test', password='memory-test-password')
        self.other = get_user_model().objects.create_user(username='other-memory-owner', email='other@example.test')
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {Token.objects.get_or_create(user=self.user)[0].key}')
        self.draft = {'title': 'The ride home', 'body': 'Windows down after the show.', 'occurredAt': '2026-09-15T21:00:00Z',
                      'place': 'Brooklyn', 'people': ['Sam'], 'tags': ['summer'], 'songs': [
                          {'id': str(uuid.uuid4()), 'provider': 'spotify', 'providerTrackID': 'song-id',
                           'title': 'A song', 'artist': 'An artist', 'deepLink': 'spotify:track:song-id',
                           'segmentStartSeconds': 12, 'segmentEndSeconds': 30}]}

    def create_memory(self, draft=None):
        response = self.client.post('/api/v1/vibe/memories/', draft or self.draft, format='json')
        self.assertEqual(response.status_code, 201, response.data)
        return response.data

    def test_authenticated_multimedia_create_browse_edit_and_delete(self):
        image = SimpleUploadedFile('sunset.png', b'\x89PNG\r\n\x1a\n' + b'fixture', content_type='image/png')
        upload = self.client.post('/api/v1/vibe/memory-media/', {'file': image}, format='multipart')
        self.assertEqual(upload.status_code, 201, upload.data)
        memory = self.create_memory({**self.draft, 'mediaIDs': [upload.data['id']]})
        self.assertEqual(memory['media'][0]['kind'], 'photo')
        self.assertEqual(memory['classification']['status'], 'unavailable')
        self.assertEqual(memory['generatedTags'], [])
        self.assertEqual(self.client.get(upload.data['url']).status_code, 200)
        listing = self.client.get('/api/v1/vibe/memories/').data
        self.assertEqual(listing['memories'][0]['id'], memory['id'])
        detail = f"/api/v1/vibe/memories/{memory['id']}/"
        patched = self.client.patch(detail, {'tags': ['summer', 'road trip']}, format='json')
        self.assertEqual(patched.status_code, 200, patched.data)
        self.assertEqual(self.client.get('/api/v1/vibe/memory-tags/').data['tags'], ['road trip', 'summer'])
        signals = memory_recommendation_context(self.user)
        self.assertEqual(signals[0]['tags'], ['summer', 'road trip'])
        self.assertEqual(signals[0]['songs'][0]['providerTrackID'], 'song-id')
        context = self.client.get('/api/v1/vibe/memory-recommendation-context/').data
        self.assertEqual(context['songSeeds'][0]['memoryIDs'], [memory['id']])
        self.assertEqual(context['tagSignals'][0]['weight'], 1)
        insights = self.client.get('/api/v1/vibe/memory-insights/').data
        self.assertEqual(insights['memoryCount'], 1)
        self.assertIn('Brooklyn', insights['prompt'])
        self.assertEqual(self.client.delete(detail).status_code, 204)
        self.assertFalse(MemoryMedia.objects.exists())

    def test_no_auth_and_cross_account_access(self):
        memory = self.create_memory()
        detail = f"/api/v1/vibe/memories/{memory['id']}/"
        self.client.credentials()
        self.assertEqual(self.client.get('/api/v1/vibe/memories/').status_code, 401)
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.get(detail).status_code, 404)
        self.assertEqual(self.client.patch(detail, {'tags': ['stolen']}, format='json').status_code, 404)
        self.assertEqual(self.client.delete(detail).status_code, 404)
        self.assertEqual(self.client.get('/api/v1/vibe/memory-tags/').data['tags'], [])
        self.assertEqual(self.client.get('/api/v1/vibe/memory-recommendation-context/').data['songSeeds'], [])
        self.assertEqual(self.client.get('/api/v1/vibe/memories/').data['memories'], [])

    def test_attachment_cannot_be_read_or_claimed_by_other_user(self):
        media = MemoryMedia.objects.create(user=self.other, kind='photo', filename='private.png',
                                           content_type='image/png', content=b'private', size=7)
        self.assertEqual(self.client.get(f'/api/v1/vibe/memory-media/{media.id}/content/').status_code, 404)
        result = self.client.post('/api/v1/vibe/memories/', {**self.draft, 'mediaIDs': [str(media.id)]}, format='json')
        self.assertEqual(result.status_code, 400)
        self.assertFalse(MusicMemory.objects.exists())

    @patch('vibe.memory_views.classify_memory')
    def test_classification_before_persistence_and_user_tag_removal(self, classify):
        def classified(draft):
            self.assertFalse(MusicMemory.objects.exists())
            return ['nostalgia', 'summer'], {'status': 'complete', 'provider': 'jev'}
        classify.side_effect = classified
        memory = self.create_memory({**self.draft, 'excludedTags': ['nostalgia']})
        self.assertEqual(memory['tags'], ['summer'])
        self.assertEqual(memory['generatedTags'], ['nostalgia', 'summer'])
        classify.assert_called_once()
        response = self.client.patch(f"/api/v1/vibe/memories/{memory['id']}/", {'tags': ['custom']}, format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data['tags'], ['custom'])
        self.assertIn('summer', response.data['excludedTags'])
        classify.assert_called_once()

    def test_chronological_pagination_and_connections(self):
        first = self.create_memory({**self.draft, 'songs': self.draft['songs'] * 2})
        second = self.create_memory({**self.draft, 'occurredAt': '2026-09-16T21:00:00Z'})
        page = self.client.get('/api/v1/vibe/memories/?limit=1').data
        self.assertEqual(page['memories'][0]['id'], second['id'])
        self.assertEqual(page['nextOffset'], 1)
        self.assertEqual(self.client.get('/api/v1/vibe/memories/?limit=1&offset=1').data['memories'][0]['id'], first['id'])
        connections = self.client.get('/api/v1/vibe/memory-insights/').data['connections']
        self.assertTrue(any(item['kind'] == 'person' and item['count'] == 2 for item in connections))
        context = self.client.get('/api/v1/vibe/memory-recommendation-context/').data
        self.assertEqual(context['songSeeds'][0]['weight'], 2)

    def test_invalid_segments_and_nonmedia_are_rejected(self):
        song = {**self.draft['songs'][0], 'segmentEndSeconds': 1}
        result = self.client.post('/api/v1/vibe/memories/', {**self.draft, 'songs': [song]}, format='json')
        self.assertEqual(result.status_code, 400)
        upload = SimpleUploadedFile('fake.png', b'<script>bad</script>', content_type='image/png')
        self.assertEqual(self.client.post('/api/v1/vibe/memory-media/', {'file': upload}, format='multipart').status_code, 400)

    @override_settings(JEV_CLASSIFICATION_URL='https://jev.example.test/classify')
    @patch('vibe.memory_services.requests.post')
    def test_jev_adapter_contract_and_invalid_response(self, post):
        post.return_value = Mock(json=lambda: {'tags': ['Joy', 'joy']})
        tags, classification = classify_memory(self.draft)
        self.assertEqual(tags, ['Joy'])
        self.assertEqual(classification['status'], 'complete')
        self.assertFalse(post.call_args.kwargs['allow_redirects'])
        self.assertNotIn('mediaIDs', post.call_args.kwargs['json']['memory'])
        post.return_value = Mock(json=lambda: {'tags': [{'invented': True}]})
        self.assertEqual(classify_memory(self.draft), ([], {'status': 'unavailable', 'provider': 'jev'}))


    def test_title_only_create_and_removing_last_content_are_rejected(self):
        result = self.client.post('/api/v1/vibe/memories/', {
            'title': 'Just a title', 'occurredAt': self.draft['occurredAt']}, format='json')
        self.assertEqual(result.status_code, 400)
        self.assertFalse(MusicMemory.objects.exists())
        memory = self.create_memory({**self.draft, 'songs': []})
        result = self.client.patch(f"/api/v1/vibe/memories/{memory['id']}/", {'body': ''}, format='json')
        self.assertEqual(result.status_code, 400)
        self.assertEqual(MusicMemory.objects.get(pk=memory['id']).body, self.draft['body'])

    def test_video_upload_is_private_and_content_type_comes_from_bytes(self):
        video_bytes = b'\x00\x00\x00\x18ftypmp42' + b'\x00' * 24
        video = SimpleUploadedFile('clip.mp4', video_bytes, content_type='text/html')
        upload = self.client.post('/api/v1/vibe/memory-media/', {'file': video}, format='multipart')
        self.assertEqual(upload.status_code, 201, upload.data)
        self.assertEqual(upload.data['kind'], 'video')
        self.assertEqual(upload.data['contentType'], 'video/mp4')
        memory = self.create_memory({**self.draft, 'mediaIDs': [upload.data['id']]})
        downloaded = self.client.get(upload.data['url'])
        self.assertEqual(downloaded['Content-Type'], 'video/mp4')
        self.assertEqual(downloaded['Cache-Control'], 'private, no-store')
        self.assertEqual(downloaded['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(b''.join(downloaded.streaming_content), video_bytes)
        self.assertEqual(self.client.delete(upload.data['url']).status_code, 404)
        self.assertTrue(MemoryMedia.objects.filter(memory_id=memory['id']).exists())
        self.client.credentials()
        self.assertEqual(self.client.get(upload.data['url']).status_code, 401)
        self.assertEqual(self.client.delete(upload.data['url']).status_code, 401)

    def test_unattached_media_delete_is_owner_only_and_idempotently_missing(self):
        media = MemoryMedia.objects.create(user=self.user, kind='photo', filename='draft.png',
                                           content_type='image/png', content=b'private', size=7)
        url = f'/api/v1/vibe/memory-media/{media.id}/content/'
        self.client.force_authenticate(self.other)
        self.assertEqual(self.client.delete(url).status_code, 404)
        self.assertTrue(MemoryMedia.objects.filter(pk=media.pk).exists())
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.delete(url).status_code, 204)
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(self.client.delete(url).status_code, 404)

    @override_settings(JEV_CLASSIFICATION_URL='https://jev.example.test/classify')
    @patch('vibe.memory_services.requests.post', side_effect=requests.Timeout)
    def test_jev_outage_saves_explicit_unavailable_status_without_fake_tags(self, post):
        preview = self.client.post('/api/v1/vibe/memories/classify/', self.draft, format='json')
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.data, {'tags': [], 'classification': {'status': 'unavailable', 'provider': 'jev'}})
        self.assertFalse(MusicMemory.objects.exists())
        memory = self.create_memory()
        self.assertEqual(memory['classification'], {'status': 'unavailable', 'provider': 'jev'})
        self.assertEqual(memory['generatedTags'], [])
        self.assertEqual(memory['tags'], ['summer'])
        self.assertEqual(post.call_count, 2)

    def test_segment_bounds_and_partial_edits_preserve_other_fields(self):
        for invalid in (-1, 604801):
            with self.subTest(invalid=invalid):
                song = {**self.draft['songs'][0], 'segmentStartSeconds': invalid}
                result = self.client.post('/api/v1/vibe/memories/', {**self.draft, 'songs': [song]}, format='json')
                self.assertEqual(result.status_code, 400)
        memory = self.create_memory()
        url = f"/api/v1/vibe/memories/{memory['id']}/"
        self.assertEqual(self.client.patch(url, {'body': 'A new detail'}, format='json').status_code, 200)
        result = self.client.patch(url, {'place': 'Queens'}, format='json')
        self.assertEqual(result.status_code, 200, result.data)
        self.assertEqual(result.data['body'], 'A new detail')
        self.assertEqual(result.data['place'], 'Queens')
        self.assertEqual(result.data['tags'], ['summer'])


    def test_unicode_casefold_expansion_stays_reusable_without_duplicate_tags(self):
        tag = 'ß' * 60
        first = self.create_memory({**self.draft, 'tags': [tag]})
        second = self.create_memory({**self.draft, 'tags': [tag]})
        self.assertEqual(first['tags'], [tag])
        self.assertEqual(second['tags'], [tag])
        self.assertEqual(self.client.get('/api/v1/vibe/memory-tags/').data['tags'], [tag])

    def test_tag_vocabulary_uses_canonical_memory_tags(self):
        memory = self.create_memory({**self.draft, 'tags': [' Road trip ', 'road trip']})
        self.assertEqual(memory['tags'], ['Road trip'])
        self.assertEqual(self.client.get('/api/v1/vibe/memory-tags/').data['tags'], ['Road trip'])
