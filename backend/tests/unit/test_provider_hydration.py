import tempfile
import uuid
from datetime import timedelta
from io import StringIO
from unittest import mock

import requests
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import OperationalError
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from mlcore.management.commands.hydrate_spotify_from_isrc import wait_for_database
from mlcore.models import CanonicalItem, CanonicalItemAlias, ProviderHydrationItem, ProviderHydrationRun
from mlcore.services.provider_hydration import (
    ProviderHydrationError,
    IncrementalSeedResult,
    ReconciliationResult,
    RequestPacer,
    SpotifyCandidate,
    SpotifyClient,
    claim_hydration_item,
    hydrate_spotify_item,
    normalize_isrc,
    reconcile_stale_hydration_state,
    seed_spotify_hydration_queue_incrementally,
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


class DatabaseHealthWaitTests(SimpleTestCase):
    @mock.patch('mlcore.management.commands.hydrate_spotify_from_isrc.connection')
    def test_retries_until_database_query_succeeds(self, database):
        database.ensure_connection.side_effect = [OperationalError('starting'), None]
        cursor = database.cursor.return_value.__enter__.return_value
        sleep = mock.Mock()

        wait_for_database(
            timeout_seconds=5,
            interval_seconds=1,
            sleep=sleep,
            monotonic=mock.Mock(side_effect=[0, 0]),
        )

        self.assertEqual(database.ensure_connection.call_count, 2)
        database.close.assert_called_once_with()
        sleep.assert_called_once_with(1)
        cursor.execute.assert_called_once_with('SELECT 1')

    @mock.patch('mlcore.management.commands.hydrate_spotify_from_isrc.connection')
    def test_raises_after_database_wait_timeout(self, database):
        database.ensure_connection.side_effect = OperationalError('still down')

        with self.assertRaisesMessage(CommandError, 'Database did not become healthy within 1s'):
            wait_for_database(
                timeout_seconds=1,
                interval_seconds=1,
                sleep=mock.Mock(),
                monotonic=mock.Mock(side_effect=[0, 2]),
            )


class HydrationCommandTests(TestCase):
    @mock.patch('mlcore.management.commands.hydrate_spotify_from_isrc.claim_hydration_item')
    @mock.patch('mlcore.management.commands.hydrate_spotify_from_isrc.SpotifyClient')
    @mock.patch('mlcore.management.commands.hydrate_spotify_from_isrc.seed_spotify_hydration_queue')
    @mock.patch(
        'mlcore.management.commands.hydrate_spotify_from_isrc.'
        'seed_spotify_hydration_queue_incrementally'
    )
    @mock.patch('mlcore.management.commands.hydrate_spotify_from_isrc.reconcile_stale_hydration_state')
    @mock.patch('mlcore.management.commands.hydrate_spotify_from_isrc.spotify_worker_lock')
    @mock.patch('mlcore.management.commands.hydrate_spotify_from_isrc.wait_for_database')
    def test_production_cli_finalizes_run_before_releasing_lock_and_inherits_cursor(
        self,
        wait_for_database_mock,
        worker_lock_mock,
        reconcile_mock,
        incremental_seed_mock,
        full_seed_mock,
        spotify_client_mock,
        claim_mock,
    ):
        previous = ProviderHydrationRun.objects.create(
            provider='spotify',
            status='succeeded',
            completed_at=timezone.now(),
            metadata={'incremental_seed_cursor': 'OLD_CURSOR'},
        )
        observed = {}

        class ObservingLock:
            def __enter__(self):
                return True

            def __exit__(self, exc_type, exc, traceback):
                current = ProviderHydrationRun.objects.exclude(id=previous.id).get()
                observed['status_at_unlock'] = current.status
                observed['completed_at_at_unlock'] = current.completed_at

        worker_lock_mock.return_value = ObservingLock()
        reconcile_mock.return_value = ReconciliationResult(stale_runs=0, reclaimed_items=0)
        incremental_seed_mock.return_value = IncrementalSeedResult(
            scanned=10,
            created=3,
            next_cursor='NEW_CURSOR',
            pass_complete=False,
        )
        claim_mock.return_value = None
        output = StringIO()

        call_command(
            'hydrate_spotify_from_isrc',
            skip_seed=True,
            rps=1,
            max_items=1,
            json=True,
            metrics_path='',
            stdout=output,
        )

        wait_for_database_mock.assert_called_once()
        reconcile_mock.assert_called_once()
        full_seed_mock.assert_not_called()
        incremental_seed_mock.assert_called_once_with(
            after_source_id='OLD_CURSOR',
            scan_limit=10_000,
        )
        spotify_client_mock.assert_called_once()
        self.assertEqual(observed['status_at_unlock'], 'succeeded')
        self.assertIsNotNone(observed['completed_at_at_unlock'])
        current = ProviderHydrationRun.objects.exclude(id=previous.id).get()
        self.assertEqual(current.metadata['incremental_seed_cursor'], 'NEW_CURSOR')
        self.assertEqual(current.metadata['incremental_seed_created_total'], 3)


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

    def test_stale_state_reconciliation_fails_run_and_reclaims_lease(self):
        self.item.status = 'running'
        self.item.leased_by = 'dead-worker'
        self.item.lease_expires_at = timezone.now() + timedelta(minutes=2)
        self.item.last_run = self.run
        self.item.save()

        result = reconcile_stale_hydration_state(provider='spotify', reconciled_by='replacement')

        self.assertEqual(result.stale_runs, 1)
        self.assertEqual(result.reclaimed_items, 1)
        self.run.refresh_from_db()
        self.item.refresh_from_db()
        self.assertEqual(self.run.status, 'failed')
        self.assertEqual(self.run.metadata['reconciled_by'], 'replacement')
        self.assertIsNotNone(self.run.completed_at)
        self.assertEqual(self.item.status, 'pending')
        self.assertEqual(self.item.leased_by, '')
        self.assertIsNone(self.item.lease_expires_at)

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

    def test_incremental_seeding_advances_a_bounded_cursor(self):
        for isrc in ('AAA000000001', 'BBB000000002'):
            canonical = CanonicalItem.objects.create(
                id=uuid.uuid4(),
                item_type='recording_mbid',
                canonical_key=f'recording_mbid:{uuid.uuid4()}',
            )
            CanonicalItemAlias.objects.create(
                canonical_item=canonical,
                source='isrc',
                resource_type='recording',
                source_id=isrc,
                status='active',
            )

        first = seed_spotify_hydration_queue_incrementally(scan_limit=1)
        second = seed_spotify_hydration_queue_incrementally(
            after_source_id=first.next_cursor,
            scan_limit=1,
        )
        completed = seed_spotify_hydration_queue_incrementally(
            after_source_id=second.next_cursor,
            scan_limit=1,
        )

        self.assertEqual((first.scanned, first.created, first.pass_complete), (1, 1, False))
        self.assertEqual((second.scanned, second.created, second.pass_complete), (1, 1, False))
        self.assertEqual((completed.scanned, completed.created, completed.pass_complete), (0, 0, True))
        self.assertEqual(completed.next_cursor, '')

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
