import tempfile
import uuid
from unittest import mock

import requests
from django.test import SimpleTestCase, TestCase, override_settings

from mlcore.models import CanonicalItem, CanonicalItemAlias, ProviderHydrationItem, ProviderHydrationRun
from mlcore.services.provider_hydration import (
    ProviderHydrationError,
    RequestPacer,
    SpotifyCandidate,
    SpotifyClient,
    claim_hydration_item,
    hydrate_spotify_item,
    normalize_isrc,
    write_hydration_metrics,
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, headers=None):
        self.status_code = status_code
        self._payload = payload or {}
        self.headers = headers or {}

    def json(self):
        return self._payload


class SpotifyClientTests(SimpleTestCase):
    def test_search_accepts_only_exact_returned_isrc(self):
        session = mock.Mock()
        session.post.return_value = FakeResponse(payload={'access_token': 'token', 'expires_in': 3600})
        session.get.return_value = FakeResponse(payload={'tracks': {'items': [
            self._track('exact', 'USRC17607839'),
            self._track('false-positive', 'GBAYE0601696'),
        ]}})

        candidates = SpotifyClient('id', 'secret', session=session).search_isrc('US-RC1-76-07839')

        self.assertEqual([candidate.track_id for candidate in candidates], ['exact'])
        self.assertEqual(session.get.call_args.kwargs['params']['limit'], 10)

    def test_search_refreshes_token_once_after_401(self):
        session = mock.Mock()
        session.post.side_effect = [
            FakeResponse(payload={'access_token': 'old', 'expires_in': 3600}),
            FakeResponse(payload={'access_token': 'new', 'expires_in': 3600}),
        ]
        session.get.side_effect = [FakeResponse(status_code=401), FakeResponse(payload={'tracks': {'items': []}})]

        self.assertEqual(SpotifyClient('id', 'secret', session=session).search_isrc('USRC17607839'), [])
        self.assertEqual(session.post.call_count, 2)

    def test_search_surfaces_retry_after_on_429(self):
        session = mock.Mock()
        session.post.return_value = FakeResponse(payload={'access_token': 'token', 'expires_in': 3600})
        session.get.return_value = FakeResponse(status_code=429, headers={'Retry-After': '17'})

        with self.assertRaises(ProviderHydrationError) as raised:
            SpotifyClient('id', 'secret', session=session).search_isrc('USRC17607839')

        self.assertEqual(raised.exception.http_status, 429)
        self.assertEqual(raised.exception.retry_after, 17)

    def test_network_errors_are_retryable(self):
        session = mock.Mock()
        session.post.return_value = FakeResponse(payload={'access_token': 'token', 'expires_in': 3600})
        session.get.side_effect = requests.Timeout('slow')

        with self.assertRaises(ProviderHydrationError) as raised:
            SpotifyClient('id', 'secret', session=session).search_isrc('USRC17607839')

        self.assertTrue(raised.exception.retryable)

    @staticmethod
    def _track(track_id, isrc):
        return {
            'id': track_id,
            'uri': f'spotify:track:{track_id}',
            'name': 'Track',
            'artists': [{'name': 'Artist'}],
            'duration_ms': 1234,
            'popularity': 50,
            'external_ids': {'isrc': isrc},
        }


class RequestPacerTests(SimpleTestCase):
    def test_rate_limit_halves_rate_and_honors_retry_after(self):
        clock = mock.Mock(side_effect=[10.0])
        pacer = RequestPacer(4, sleep=mock.Mock(), monotonic=clock, jitter=lambda _a, _b: 0.5)

        pacer.rate_limited(20)

        self.assertEqual(pacer.current_rps, 2)
        self.assertEqual(pacer._next_request_at, 30.5)

    def test_normalize_isrc_removes_punctuation(self):
        self.assertEqual(normalize_isrc('us-rc1-76-07839'), 'USRC17607839')


@override_settings(SPOTIFY_HYDRATION_MAX_ATTEMPTS=3)
class HydrationStateTests(TestCase):
    def setUp(self):
        self.canonical = CanonicalItem.objects.create(
            id=uuid.uuid4(), item_type='recording_mbid', canonical_key=f'recording_mbid:{uuid.uuid4()}',
        )
        self.run = ProviderHydrationRun.objects.create(provider='spotify')
        self.item = ProviderHydrationItem.objects.create(
            canonical_item=self.canonical,
            provider='spotify',
            identifier_type='isrc',
            identifier='USRC17607839',
        )

    def test_exact_match_creates_active_alias(self):
        client = mock.Mock(search_isrc=mock.Mock(return_value=[self._candidate('spotify-id')]))

        outcome = hydrate_spotify_item(self.item, run=self.run, client=client)

        self.assertEqual(outcome, 'matched')
        alias = CanonicalItemAlias.objects.get(source='spotify', source_id='spotify-id')
        self.assertEqual(alias.canonical_item, self.canonical)
        self.assertEqual(alias.metadata['match_isrc'], 'USRC17607839')
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, 'matched')

    def test_no_match_is_terminal(self):
        outcome = hydrate_spotify_item(self.item, run=self.run, client=mock.Mock(search_isrc=lambda _isrc: []))
        self.item.refresh_from_db()
        self.assertEqual(outcome, 'no_match')
        self.assertEqual(self.item.status, 'no_match')

    def test_multiple_exact_matches_are_quarantined(self):
        client = mock.Mock(search_isrc=mock.Mock(return_value=[self._candidate('one'), self._candidate('two')]))
        outcome = hydrate_spotify_item(self.item, run=self.run, client=client)
        self.assertEqual(outcome, 'ambiguous')
        self.assertFalse(CanonicalItemAlias.objects.filter(source='spotify').exists())

    def test_existing_alias_on_other_item_is_quarantined(self):
        other = CanonicalItem.objects.create(
            id=uuid.uuid4(), item_type='recording_mbid', canonical_key=f'recording_mbid:{uuid.uuid4()}',
        )
        CanonicalItemAlias.objects.create(
            canonical_item=other, source='spotify', resource_type='track', source_id='spotify-id',
        )
        outcome = hydrate_spotify_item(
            self.item, run=self.run, client=mock.Mock(search_isrc=lambda _isrc: [self._candidate('spotify-id')]),
        )
        self.assertEqual(outcome, 'ambiguous')

    def test_retryable_error_preserves_item_for_future_claim(self):
        client = mock.Mock(search_isrc=mock.Mock(side_effect=ProviderHydrationError('busy', http_status=503)))
        with self.assertRaises(ProviderHydrationError):
            hydrate_spotify_item(self.item, run=self.run, client=client)
        self.item.refresh_from_db()
        self.assertEqual(self.item.status, 'retry')
        self.assertIsNotNone(self.item.next_attempt_at)

    def test_expired_lease_is_reclaimed(self):
        self.item.status = 'running'
        self.item.lease_expires_at = self.run.started_at
        self.item.save()
        claimed = claim_hydration_item(run=self.run, worker_id='replacement')
        self.assertEqual(claimed.id, self.item.id)
        self.assertEqual(claimed.leased_by, 'replacement')

    def test_metrics_include_backlog_and_eta(self):
        self.run.attempted_count = 10
        self.run.matched_count = 7
        self.run.save()
        with tempfile.TemporaryDirectory() as directory:
            path = f'{directory}/hydration.prom'
            write_hydration_metrics(self.run, path=path, backlog=100)
            payload = open(path, encoding='ascii').read()
        self.assertIn('mlcore_provider_hydration_backlog', payload)
        self.assertIn('mlcore_provider_hydration_eta_seconds', payload)

    @staticmethod
    def _candidate(track_id):
        return SpotifyCandidate(
            track_id=track_id,
            uri=f'spotify:track:{track_id}',
            isrc='USRC17607839',
            name='Track',
            artists=('Artist',),
            duration_ms=1234,
            popularity=50,
        )
