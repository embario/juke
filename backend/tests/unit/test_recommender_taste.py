from django.test import SimpleTestCase

from juke_auth.models import JukeUser, MusicProfile
from recommender.services import taste


class RecommenderTasteTests(SimpleTestCase):
    def test_normalized_list_strips_and_deduplicates(self):
        values = ['  Tool  ', 'Opeth', 'tool', '', None]

        result = taste._normalized_list(values)

        self.assertEqual(result, ['Opeth', 'Tool', 'tool'])

    def test_mixed_payload_normalizes_inputs(self):
        payload = taste.mixed_payload(
            artists=[' Mastodon', 'Opeth', 'mastodon'],
            albums=None,
            tracks=['', None, 'Lateralus'],
            genres=['prog', 'doom', 'prog'],
        )

        self.assertEqual(payload['artists'], ['Mastodon', 'Opeth', 'mastodon'])
        self.assertEqual(payload['albums'], [])
        self.assertEqual(payload['tracks'], ['Lateralus'])
        self.assertEqual(payload['genres'], ['doom', 'prog'])

    def test_profile_to_payload_reads_music_profile(self):
        user = JukeUser(username='taste-user', email='taste@example.com')
        profile = MusicProfile(
            user=user,
            favorite_artists=['Tool', ' Opeth '],
            favorite_albums=None,
            favorite_tracks=['Lateralus', 'lateralus'],
            favorite_genres=['prog'],
        )

        payload = taste.profile_to_payload(profile)

        self.assertEqual(payload['artists'], ['Opeth', 'Tool'])
        self.assertEqual(payload['albums'], [])
        self.assertEqual(payload['tracks'], ['Lateralus', 'lateralus'])
        self.assertEqual(payload['genres'], ['prog'])
