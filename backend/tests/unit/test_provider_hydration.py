import tempfile
from types import SimpleNamespace
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
    AdaptiveRateController,
    ProviderHydrationError,
    IncrementalSeedResult,
    ReconciliationResult,
    RequestPacer,
    SpotifyCandidate,
    SpotifyClient,
    SpotifyHydrationQuotaGuard,
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
        session.get.return_value = FakeResponse(
            status_code=429,
            headers={'Retry-After': '17'},
            payload={'error': {'reason': 'QUOTA_EXCEEDED'}},
        )

        with self.assertRaises(ProviderHydrationError) as raised:
            SpotifyClient('id', 'secret', session=session).search_isrc('USRC17607839')

        self.assertEqual(raised.exception.http_status, 429)
        self.assertEqual(raised.exception.retry_after, 17)
        self.assertEqual(raised.exception.reason, 'QUOTA_EXCEEDED')

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


class SpotifyHydrationQuotaGuardTests(TestCase):
    def setUp(self):
        self.clock = [1_000.0]
        self.guard = SpotifyHydrationQuotaGuard(2, 100, now=lambda: self.clock[0])
        self.run = ProviderHydrationRun.objects.create(
            provider='spotify',
            metadata={self.guard.metadata_key: self.guard.initial_state()},
        )

    def test_budget_smooths_requested_rate_and_pauses_at_limit(self):
        self.assertEqual(self.guard.effective_rps(1), 0.02)

        self.guard.record_request(self.run)
        self.guard.record_request(self.run)

        self.assertEqual(self.guard.delay_seconds(self.run), 100)
        self.clock[0] = 1_101.0
        self.assertEqual(self.guard.delay_seconds(self.run), 0)
        self.run.refresh_from_db()
        self.assertEqual(
            self.run.metadata[self.guard.metadata_key]['requests_used'],
            0,
        )

    def test_provider_retry_after_survives_run_restart(self):
        self.guard.rate_limited(
            self.run,
            retry_after=45,
            reason='QUOTA_EXCEEDED',
        )
        self.run.refresh_from_db()
        inherited = self.guard.initial_state(self.run.metadata)
        replacement = ProviderHydrationRun.objects.create(
            provider='spotify',
            metadata={self.guard.metadata_key: inherited},
        )

        self.assertEqual(self.guard.delay_seconds(replacement), 45)
        self.assertEqual(inherited['last_limit_reason'], 'QUOTA_EXCEEDED')


class FakeRun:
    """Stands in for ProviderHydrationRun where no database is needed."""

    def __init__(self, metadata=None):
        self.metadata = metadata or {}

    def save(self, **_kwargs):
        pass


def make_controller(clock, **overrides):
    options = dict(
        floor_rps=0.05, ceiling_rps=0.25, start_rps=0.1, adaptive=True,
        step_rps=0.05, ramp_interval_seconds=600, server_error_streak=3, now=lambda: clock[0],
    )
    options.update(overrides)
    return AdaptiveRateController(**options)


class AdaptiveRateControllerTests(SimpleTestCase):
    def setUp(self):
        self.clock = [1_000.0]
        self.run = FakeRun()

    def controller(self, **overrides):
        controller = make_controller(self.clock, **overrides)
        self.run.metadata = {controller.metadata_key: controller.initial_state()}
        return controller

    def test_rate_rises_one_step_per_quiet_period_up_to_the_ceiling(self):
        controller = self.controller()
        observed = [controller.rps(self.run)]
        for _ in range(5):
            controller.success(self.run)          # inside the quiet period: nothing changes
            self.assertAlmostEqual(controller.rps(self.run), observed[-1])
            self.clock[0] += 600
            controller.success(self.run)
            observed.append(round(controller.rps(self.run), 4))
        self.assertEqual(observed, [0.1, 0.15, 0.2, 0.25, 0.25, 0.25])

    def test_429_halves_the_rate_down_to_the_floor_and_restarts_the_quiet_period(self):
        controller = self.controller(start_rps=0.2)
        controller.rate_limited(self.run)
        self.assertAlmostEqual(controller.rps(self.run), 0.1)
        self.clock[0] += 599
        controller.success(self.run)
        self.assertAlmostEqual(controller.rps(self.run), 0.1, msg='the quiet period restarted at the 429')
        self.clock[0] += 1
        controller.success(self.run)
        self.assertAlmostEqual(controller.rps(self.run), 0.15)
        for _ in range(6):
            controller.rate_limited(self.run)
        self.assertEqual(controller.rps(self.run), 0.05)
        self.assertEqual(self.run.metadata[controller.metadata_key]['rate_limited_total'], 7)

    def test_a_streak_of_5xx_backs_off_but_a_success_resets_the_streak(self):
        controller = self.controller(start_rps=0.2)
        controller.server_error(self.run)
        controller.server_error(self.run)
        controller.success(self.run)
        controller.server_error(self.run)
        controller.server_error(self.run)
        self.assertEqual(controller.rps(self.run), 0.2)
        controller.server_error(self.run)  # third in a row
        self.assertAlmostEqual(controller.rps(self.run), 0.15)
        self.assertEqual(self.run.metadata[controller.metadata_key]['server_error_total'], 5)

    def test_without_an_operator_ceiling_the_rate_never_moves(self):
        controller = self.controller(adaptive=False, start_rps=0.058, ceiling_rps=0.058, floor_rps=0.001)
        for _ in range(3):
            self.clock[0] += 10_000
            controller.success(self.run)
        controller.rate_limited(self.run)
        for _ in range(9):
            controller.server_error(self.run)
        self.assertEqual(controller.rps(self.run), 0.058)
        state = self.run.metadata[controller.metadata_key]
        self.assertEqual((state['rate_limited_total'], state['server_error_total']), (1, 9))

    def test_a_restart_resumes_from_the_learned_rate_clamped_to_the_configured_bounds(self):
        controller = self.controller()
        self.clock[0] += 1_200
        controller.success(self.run)
        learned = controller.rps(self.run)
        self.assertGreater(learned, 0.1)
        previous = dict(self.run.metadata)

        restarted = make_controller(self.clock)
        self.assertEqual(restarted.initial_state(previous)['learned_rps'], learned)
        lowered = make_controller(self.clock, ceiling_rps=0.12)
        self.assertEqual(lowered.initial_state(previous)['learned_rps'], 0.12)
        raised_floor = make_controller(self.clock, floor_rps=0.2)
        self.assertEqual(raised_floor.initial_state(previous)['learned_rps'], 0.2)
        not_adaptive = make_controller(self.clock, adaptive=False, start_rps=0.058, ceiling_rps=0.058)
        self.assertEqual(not_adaptive.initial_state(previous)['learned_rps'], 0.058)

    @override_settings(
        SPOTIFY_HYDRATION_MAX_RPS=0, SPOTIFY_HYDRATION_MIN_RPS=0, SPOTIFY_HYDRATION_REQUEST_BUDGET=5000,
        SPOTIFY_HYDRATION_BUDGET_WINDOW_SECONDS=86400,
    )
    def test_defaults_keep_todays_rate_and_do_not_ramp(self):
        guard = SpotifyHydrationQuotaGuard(5000, 86400)
        controller = AdaptiveRateController.from_settings(guard, 1.0)
        self.assertFalse(controller.adaptive)
        self.assertAlmostEqual(controller.start_rps, 5000 / 86400)
        self.assertAlmostEqual(controller.ceiling_rps, 5000 / 86400)

    @override_settings(
        SPOTIFY_HYDRATION_MAX_RPS=2.0, SPOTIFY_HYDRATION_MIN_RPS=0.02, SPOTIFY_HYDRATION_REQUEST_BUDGET=5000,
        SPOTIFY_HYDRATION_BUDGET_WINDOW_SECONDS=86400,
    )
    def test_the_budget_stays_the_hard_ceiling_even_when_the_operator_sets_a_higher_max(self):
        guard = SpotifyHydrationQuotaGuard(5000, 86400)
        controller = AdaptiveRateController.from_settings(guard, 1.0)
        self.assertTrue(controller.adaptive)
        self.assertAlmostEqual(controller.ceiling_rps, 5000 / 86400)
        guard = SpotifyHydrationQuotaGuard(100_000, 86400)
        self.assertAlmostEqual(AdaptiveRateController.from_settings(guard, 1.0).ceiling_rps, 100_000 / 86400)
        self.assertAlmostEqual(AdaptiveRateController.from_settings(guard, 1.0).start_rps, 1.0)
        unlimited = SpotifyHydrationQuotaGuard(0, 86400)
        self.assertEqual(AdaptiveRateController.from_settings(unlimited, 1.0).ceiling_rps, 2.0)


class AdaptiveRateRestartTests(TestCase):
    def test_learned_rate_survives_a_new_run_through_the_database(self):
        clock = [0.0]
        controller = make_controller(clock)
        first = ProviderHydrationRun.objects.create(
            provider='spotify', metadata={controller.metadata_key: controller.initial_state()},
        )
        clock[0] += 700
        controller.success(first)
        controller.server_error(first)
        first.refresh_from_db()
        learned = first.metadata[controller.metadata_key]['learned_rps']
        self.assertAlmostEqual(learned, 0.15)

        previous = ProviderHydrationRun.objects.filter(provider='spotify').first()
        second = ProviderHydrationRun.objects.create(
            provider='spotify',
            metadata={controller.metadata_key: make_controller(clock).initial_state(previous.metadata)},
        )
        self.assertAlmostEqual(make_controller(clock).rps(second), learned)


class ServerErrorBudgetTests(TestCase):
    def test_a_burst_of_502s_leaves_the_budget_substantially_intact(self):
        guard = SpotifyHydrationQuotaGuard(1000, 86400, now=lambda: 1_000.0)
        run = ProviderHydrationRun.objects.create(
            provider='spotify', metadata={guard.metadata_key: guard.initial_state()},
        )
        for _ in range(100):
            guard.record_request(run)
            guard.refund_request(run, charged_weight=0.1)
        run.refresh_from_db()
        self.assertAlmostEqual(run.metadata[guard.metadata_key]['requests_used'], 10.0)

    def test_refund_never_drives_usage_below_zero(self):
        guard = SpotifyHydrationQuotaGuard(1000, 86400, now=lambda: 1_000.0)
        run = ProviderHydrationRun.objects.create(
            provider='spotify', metadata={guard.metadata_key: guard.initial_state()},
        )
        guard.refund_request(run, charged_weight=0.0)
        self.assertEqual(run.metadata[guard.metadata_key]['requests_used'], 0.0)


class AdaptiveCommandTests(TestCase):
    def run_command(self, errors, **settings_overrides):
        items = [SimpleNamespace(identifier=f'ISRC{n}') for n in range(len(errors))]
        queue = items + [None]
        base = 'mlcore.management.commands.hydrate_spotify_from_isrc.'
        with override_settings(**settings_overrides), \
                mock.patch(base + 'wait_for_database'), \
                mock.patch(base + 'spotify_worker_lock') as lock, \
                mock.patch(base + 'reconcile_stale_hydration_state', return_value=ReconciliationResult(0, 0)), \
                mock.patch(base + 'SpotifyClient'), \
                mock.patch(base + 'claim_hydration_item', side_effect=queue), \
                mock.patch(base + 'hydrate_spotify_item', side_effect=errors), \
                mock.patch('time.sleep'):
            lock.return_value.__enter__.return_value = True
            call_command(
                'hydrate_spotify_from_isrc', skip_seed=True, skip_incremental_seed=True, exit_when_empty=True,
                rps=1, json=True, stdout=StringIO(), metrics_path=self.metrics_path,
            )
        return ProviderHydrationRun.objects.get()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.metrics_path = f'{self.directory.name}/hydration.prom'

    def test_502s_are_charged_at_a_reduced_weight_and_counted(self):
        errors = [ProviderHydrationError('bad gateway', http_status=502) for _ in range(20)]
        run = self.run_command(
            errors, SPOTIFY_HYDRATION_MAX_RPS=0, SPOTIFY_HYDRATION_REQUEST_BUDGET=100_000,
            SPOTIFY_HYDRATION_SERVER_ERROR_WEIGHT=0.1,
        )
        self.assertAlmostEqual(run.metadata['spotify_hydration_quota']['requests_used'], 2.0)
        self.assertEqual(run.metadata['spotify_hydration_rate']['server_error_total'], 20)
        payload = open(self.metrics_path, encoding='ascii').read()
        self.assertIn('mlcore_provider_hydration_server_error_total{provider="spotify"', payload)
        self.assertIn('mlcore_provider_hydration_learned_rps', payload)
        self.assertIn('mlcore_provider_hydration_budget_used', payload)
        self.assertIn('mlcore_provider_hydration_adaptive{provider="spotify"', payload)

    def test_a_429_cuts_the_learned_rate_and_is_counted_when_adaptive(self):
        errors = [ProviderHydrationError('limited', http_status=429, retry_after=30)]
        run = self.run_command(
            errors, SPOTIFY_HYDRATION_MAX_RPS=1.0, SPOTIFY_HYDRATION_MIN_RPS=0.001,
            SPOTIFY_HYDRATION_REQUEST_BUDGET=86_400,
        )
        state = run.metadata['spotify_hydration_rate']
        self.assertTrue(state['adaptive'])
        self.assertEqual(state['rate_limited_total'], 1)
        self.assertAlmostEqual(state['learned_rps'], 0.5)
        self.assertGreater(run.metadata['spotify_hydration_quota']['cooldown_until'], 0)


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
