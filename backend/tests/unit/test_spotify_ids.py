from django.test import SimpleTestCase

from mlcore.ingestion.listenbrainz import _extract_spotify_id, _parse_listen
from mlcore.services.canonical_items import identity_from_listenbrainz_candidates
from mlcore.services.spotify_ids import normalize_spotify_track_id

TRACK = '4uLU6hMCjMI75M1A2tKUQC'


class NormalizeSpotifyTrackIdTests(SimpleTestCase):
    def test_accepted_shapes(self):
        for value in [
            TRACK,
            f'  {TRACK} ',
            f'spotify:track:{TRACK}',
            f'SPOTIFY:TRACK:{TRACK}',
            f'https://open.spotify.com/track/{TRACK}',
            f'http://open.spotify.com/track/{TRACK}/',
            f'https://open.spotify.com/intl-de/track/{TRACK}',
            f'https://open.spotify.com/intl-pt-br/track/{TRACK}?si=abc123&utm_source=copy-link',
            f'https://open.spotify.com/track/{TRACK}#frag',
            f'open.spotify.com/track/{TRACK}',
        ]:
            with self.subTest(value=value):
                self.assertEqual(normalize_spotify_track_id(value), TRACK)

    def test_rejected_shapes(self):
        album = '1DFixLWgh2zZWvxKbdw5Rk'
        for value in [
            '',
            None,
            0,
            f'spotify:album:{album}',
            f'spotify:artist:{album}',
            f'spotify:user:someone:playlist:{album}',
            f'https://open.spotify.com/album/{album}',
            f'https://open.spotify.com/artist/{album}',
            f'https://open.spotify.com/intl-fr/playlist/{album}',
            f'https://open.spotify.com/album/{album}/track/{TRACK}',
            f'https://example.com/track/{TRACK}',
            f'https://open.spotify.com.evil.test/track/{TRACK}',
            'spotify-may',
            TRACK[:-1],
            TRACK + 'x',
            f'spotify:track:{TRACK[:-1]}',
            'not a url at all',
        ]:
            with self.subTest(value=value):
                self.assertEqual(normalize_spotify_track_id(value), '')


class ListenBrainzSpotifyEvidenceTests(SimpleTestCase):
    def test_extract_reads_every_key_and_origin_url(self):
        self.assertEqual(_extract_spotify_id({'spotify_id': f'https://open.spotify.com/track/{TRACK}'}), TRACK)
        self.assertEqual(_extract_spotify_id({'origin_url': f'https://open.spotify.com/intl-es/track/{TRACK}?si=x'}), TRACK)
        self.assertEqual(_extract_spotify_id({'media_player_track_id': f'spotify:track:{TRACK}'}), TRACK)

    def test_non_track_values_fall_through_to_the_next_key(self):
        info = {
            'spotify_id': 'https://open.spotify.com/album/1DFixLWgh2zZWvxKbdw5Rk',
            'origin_url': f'https://open.spotify.com/track/{TRACK}',
        }
        self.assertEqual(_extract_spotify_id(info), TRACK)
        self.assertEqual(_extract_spotify_id({'origin_url': 'https://example.com/song/1'}), '')

    def test_other_players_ids_are_not_mistaken_for_spotify(self):
        self.assertEqual(_extract_spotify_id({'media_player_track_id': 'local-file-9'}), '')

    def _parse(self, additional_info, **track):
        row = {
            'user_name': 'alice',
            'listened_at': 1700000000,
            'track_metadata': {
                'track_name': 'So What',
                'artist_name': 'Miles Davis',
                'additional_info': additional_info,
                **track,
            },
        }
        return _parse_listen(row)

    def test_msid_stays_the_listen_identity_and_spotify_is_evidence(self):
        parsed = self._parse(
            {'origin_url': f'https://open.spotify.com/track/{TRACK}'},
            recording_msid='11111111-2222-3333-4444-555555555555',
        )
        candidates = parsed.track_identifier_candidates
        self.assertEqual(candidates['spotify_id'], TRACK)
        self.assertEqual(parsed.metadata['spotify_track_id'], TRACK)
        identity = identity_from_listenbrainz_candidates(
            recording_mbid='',
            spotify_id=candidates['spotify_id'],
            recording_msid=parsed.recording_msid,
        )
        self.assertEqual(identity.item_type, 'recording_msid')

    def test_event_signature_ignores_how_the_id_was_spelled_only_if_raw_is_unchanged(self):
        bare = self._parse({'spotify_id': TRACK}, recording_msid='m')
        same = self._parse({'spotify_id': TRACK}, recording_msid='m')
        url = self._parse({'spotify_id': f'https://open.spotify.com/track/{TRACK}'}, recording_msid='m')
        self.assertEqual(bare.source_event_signature, same.source_event_signature)
        # Hashed from the raw client value so the existing ledger keeps deduplicating.
        self.assertNotEqual(bare.source_event_signature, url.source_event_signature)
        self.assertEqual(bare.track_identifier_candidates['spotify_id'], url.track_identifier_candidates['spotify_id'])
