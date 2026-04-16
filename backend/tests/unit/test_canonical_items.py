import uuid

from django.test import SimpleTestCase

from mlcore.services.canonical_items import (
    ITEM_TYPE_RECORDING_MBID,
    ITEM_TYPE_RECORDING_MSID,
    ITEM_TYPE_SPOTIFY_TRACK,
    identity_from_listenbrainz_candidates,
)


class CanonicalItemIdentityTests(SimpleTestCase):

    def test_prefers_recording_mbid_over_other_ids(self):
        recording_mbid = uuid.uuid4()

        identity = identity_from_listenbrainz_candidates(
            recording_mbid=str(recording_mbid),
            recording_msid='recording-msid',
            spotify_id='spotify-track-id',
        )

        self.assertIsNotNone(identity)
        self.assertEqual(identity.item_type, ITEM_TYPE_RECORDING_MBID)
        self.assertEqual(identity.canonical_key, f'{ITEM_TYPE_RECORDING_MBID}:{recording_mbid}')

    def test_prefers_recording_msid_over_spotify(self):
        identity = identity_from_listenbrainz_candidates(
            recording_msid='recording-msid',
            spotify_id='spotify-track-id',
        )

        self.assertIsNotNone(identity)
        self.assertEqual(identity.item_type, ITEM_TYPE_RECORDING_MSID)
        self.assertEqual(identity.canonical_key, f'{ITEM_TYPE_RECORDING_MSID}:recording-msid')

    def test_falls_back_to_spotify(self):
        identity = identity_from_listenbrainz_candidates(
            spotify_id='spotify-track-id',
        )

        self.assertIsNotNone(identity)
        self.assertEqual(identity.item_type, ITEM_TYPE_SPOTIFY_TRACK)
        self.assertEqual(identity.canonical_key, f'{ITEM_TYPE_SPOTIFY_TRACK}:spotify-track-id')
