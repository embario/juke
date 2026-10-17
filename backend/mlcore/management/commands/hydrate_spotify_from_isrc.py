import json
import os
import time

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import InterfaceError, OperationalError, connection
from django.utils import timezone

from mlcore.models import ProviderHydrationItem, ProviderHydrationRun
from mlcore.services.hydration_waves import WAVE_SEED_MAX_PRIORITY, expand_wave
from mlcore.services.hydration_boosts import apply_referenced_boosts, referenced_canonical_priorities
from mlcore.services.provider_hydration import (
    AdaptiveRateController,
    ProviderHydrationError,
    RequestPacer,
    SpotifyClient,
    SpotifyHydrationQuotaGuard,
    claim_hydration_item,
    hydrate_spotify_item,
    reconcile_stale_hydration_state,
    rescore_pending_priorities,
    seed_spotify_hydration_queue,
    seed_spotify_hydration_queue_incrementally,
    spotify_worker_lock,
    worker_identity,
    write_hydration_metrics,
)


DEFAULT_METRICS_PATH = '/srv/monitoring/node-exporter/textfile/mlcore_provider_hydration.prom'
DEFAULT_DATABASE_WAIT_TIMEOUT_SECONDS = 300.0
DEFAULT_DATABASE_WAIT_INTERVAL_SECONDS = 5.0
DEFAULT_INCREMENTAL_SEED_INTERVAL_SECONDS = 300.0
DEFAULT_INCREMENTAL_SEED_SCAN_LIMIT = 10_000
DEFAULT_IDLE_SLEEP_SECONDS = 5.0
DEFAULT_PRIORITY_RESCORE_INTERVAL_SECONDS = 60.0
DEFAULT_PRIORITY_RESCORE_BATCH_SIZE = 400
DEFAULT_PRIORITY_BOOST_INTERVAL_SECONDS = 300.0
DEFAULT_WAVE_INTERVAL_SECONDS = 120.0
DEFAULT_TAIL_SWEEP_EVERY = 10


def wait_for_database(*, timeout_seconds, interval_seconds, sleep=time.sleep, monotonic=time.monotonic):
    """Wait for both database connectivity and a successful trivial query."""
    deadline = monotonic() + timeout_seconds
    last_error = None
    while True:
        try:
            connection.ensure_connection()
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchone()
            return
        except (InterfaceError, OperationalError) as exc:
            last_error = exc
            connection.close()
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise CommandError(
                f'Database did not become healthy within {timeout_seconds:g}s: {last_error}'
            ) from last_error
        sleep(min(interval_seconds, remaining))


class Command(BaseCommand):
    help = 'Seed and process the durable Spotify-from-ISRC identity hydration queue.'

    def add_arguments(self, parser):
        parser.add_argument('--seed-only', action='store_true')
        parser.add_argument('--skip-seed', action='store_true')
        parser.add_argument('--seed-limit', type=int)
        parser.add_argument('--max-items', type=int)
        parser.add_argument('--rps', type=float, default=settings.SPOTIFY_HYDRATION_INITIAL_RPS)
        parser.add_argument('--batch-size', type=int, default=10_000)
        parser.add_argument(
            '--database-wait-timeout-seconds',
            type=float,
            default=DEFAULT_DATABASE_WAIT_TIMEOUT_SECONDS,
        )
        parser.add_argument(
            '--database-wait-interval-seconds',
            type=float,
            default=DEFAULT_DATABASE_WAIT_INTERVAL_SECONDS,
        )
        parser.add_argument(
            '--incremental-seed-interval-seconds',
            type=float,
            default=DEFAULT_INCREMENTAL_SEED_INTERVAL_SECONDS,
        )
        parser.add_argument(
            '--incremental-seed-scan-limit',
            type=int,
            default=DEFAULT_INCREMENTAL_SEED_SCAN_LIMIT,
        )
        parser.add_argument('--skip-incremental-seed', action='store_true')
        parser.add_argument(
            '--priority-rescore-interval-seconds',
            type=float,
            default=DEFAULT_PRIORITY_RESCORE_INTERVAL_SECONDS,
        )
        parser.add_argument(
            '--priority-rescore-batch-size',
            type=int,
            default=DEFAULT_PRIORITY_RESCORE_BATCH_SIZE,
        )
        parser.add_argument('--skip-priority-rescore', action='store_true')
        parser.add_argument(
            '--priority-boost-interval-seconds',
            type=float,
            default=DEFAULT_PRIORITY_BOOST_INTERVAL_SECONDS,
        )
        parser.add_argument('--skip-priority-boost', action='store_true')
        parser.add_argument('--wave-interval-seconds', type=float, default=DEFAULT_WAVE_INTERVAL_SECONDS)
        parser.add_argument('--wave-max-seeds', type=int, default=10)
        parser.add_argument('--wave-time-budget-seconds', type=float, default=20.0)
        parser.add_argument('--wave-fan-out', type=int, default=10)
        parser.add_argument('--wave-sibling-fan-out', type=int, default=5)
        parser.add_argument('--wave-max-updates', type=int, default=500)
        parser.add_argument('--skip-wave', action='store_true')
        parser.add_argument(
            '--tail-sweep-every',
            type=int,
            default=DEFAULT_TAIL_SWEEP_EVERY,
            help='Every Nth claim takes the oldest unscored item so the long tail is never starved (0 = off).',
        )
        parser.add_argument('--exit-when-empty', action='store_true')
        parser.add_argument('--idle-sleep-seconds', type=float, default=DEFAULT_IDLE_SLEEP_SECONDS)
        parser.add_argument('--json', action='store_true')
        parser.add_argument(
            '--metrics-path',
            default=os.environ.get('MLCORE_PROVIDER_HYDRATION_METRICS_PATH', DEFAULT_METRICS_PATH),
        )

    def handle(self, *args, **options):
        self._validate(options)
        wait_for_database(
            timeout_seconds=options['database_wait_timeout_seconds'],
            interval_seconds=options['database_wait_interval_seconds'],
        )
        seeded = 0
        worker_id = worker_identity()
        run = None
        pacer = None
        with spotify_worker_lock() as acquired:
            if not acquired:
                raise CommandError('Another Spotify hydration worker already owns the global provider lease.')
            reconciliation = reconcile_stale_hydration_state(
                provider='spotify',
                reconciled_by=worker_id,
            )
            try:
                if not options['skip_seed']:
                    seeded = seed_spotify_hydration_queue(
                        batch_size=options['batch_size'],
                        limit=options['seed_limit'],
                    )
                if options['seed_only']:
                    self._output({
                        'seeded': seeded,
                        'status': 'seeded',
                        'stale_runs_reconciled': reconciliation.stale_runs,
                        'leases_reclaimed': reconciliation.reclaimed_items,
                    }, options)
                    return

                previous_run = ProviderHydrationRun.objects.filter(provider='spotify').first()
                previous_metadata = previous_run.metadata if previous_run is not None else {}
                quota_guard = SpotifyHydrationQuotaGuard(
                    settings.SPOTIFY_HYDRATION_REQUEST_BUDGET,
                    settings.SPOTIFY_HYDRATION_BUDGET_WINDOW_SECONDS,
                )
                effective_rps = quota_guard.effective_rps(options['rps'])
                controller = AdaptiveRateController.from_settings(quota_guard, options['rps'])
                run = ProviderHydrationRun.objects.create(
                    provider='spotify',
                    requested_limit=options['max_items'],
                    configured_rps=effective_rps,
                    metadata={
                        'seeded_at_start': seeded,
                        'requested_rps': options['rps'],
                        'incremental_seed_cursor': previous_metadata.get('incremental_seed_cursor', ''),
                        'incremental_seed_scanned_total': 0,
                        'incremental_seed_created_total': 0,
                        'incremental_seed_passes_completed': 0,
                        'priority_rescore_cursor': previous_metadata.get('priority_rescore_cursor', 0),
                        'priority_rescore_scanned_total': 0,
                        'priority_rescore_updated_total': 0,
                        'priority_rescore_passes_completed': 0,
                        'stale_runs_reconciled': reconciliation.stale_runs,
                        'leases_reclaimed': reconciliation.reclaimed_items,
                        quota_guard.metadata_key: quota_guard.initial_state(previous_metadata),
                        controller.metadata_key: controller.initial_state(previous_metadata),
                    },
                )
                client = SpotifyClient(
                    settings.SPOTIFY_HYDRATION_CLIENT_ID,
                    settings.SPOTIFY_HYDRATION_CLIENT_SECRET,
                )
                if controller.adaptive:
                    pacer = RequestPacer(controller.ceiling_rps, recover=False)
                    pacer.set_rate(controller.rps(run))
                else:
                    pacer = RequestPacer(effective_rps)
                last_incremental_seed_at = time.monotonic()
                if not options['skip_incremental_seed']:
                    seeded += self._incremental_seed(run, options)
                last_priority_rescore_at = time.monotonic()
                last_wave_at = time.monotonic()
                wave_seeds = []
                claims = 0
                if not options['skip_priority_rescore']:
                    self._priority_rescore(run, options)
                while options['max_items'] is None or run.attempted_count < options['max_items']:
                    if (
                        not options['skip_incremental_seed']
                        and time.monotonic() - last_incremental_seed_at
                        >= options['incremental_seed_interval_seconds']
                    ):
                        seeded += self._incremental_seed(run, options)
                        last_incremental_seed_at = time.monotonic()
                    if (
                        not options['skip_priority_rescore']
                        and time.monotonic() - last_priority_rescore_at
                        >= options['priority_rescore_interval_seconds']
                    ):
                        self._priority_rescore(run, options)
                        last_priority_rescore_at = time.monotonic()
                    if (
                        not options['skip_wave']
                        and wave_seeds
                        and time.monotonic() - last_wave_at >= options['wave_interval_seconds']
                    ):
                        wave_seeds = self._wave(run, options, wave_seeds)
                        last_wave_at = time.monotonic()
                    quota_delay = quota_guard.delay_seconds(run)
                    if quota_delay > 0:
                        time.sleep(min(options['idle_sleep_seconds'], quota_delay))
                        continue
                    claims += 1
                    sweep_every = options['tail_sweep_every']
                    item = claim_hydration_item(
                        run=run, worker_id=worker_id, tail_sweep=bool(sweep_every and claims % sweep_every == 0),
                    )
                    if item is None:
                        if (
                            options['max_items'] is not None
                            or options['exit_when_empty']
                            or options['skip_incremental_seed']
                        ):
                            break
                        remaining = max(
                            0.0,
                            options['incremental_seed_interval_seconds']
                            - (time.monotonic() - last_incremental_seed_at),
                        )
                        time.sleep(min(options['idle_sleep_seconds'], max(remaining, 0.1)))
                        continue
                    pacer.wait()
                    quota_guard.record_request(run)
                    try:
                        outcome = hydrate_spotify_item(item, run=run, client=client)
                        if (
                            outcome == 'matched'
                            and not options['skip_wave']
                            and item.priority < WAVE_SEED_MAX_PRIORITY
                        ):
                            wave_seeds.append((item.canonical_item_id, item.priority))
                            del wave_seeds[: -10 * options['wave_max_seeds']]  # bounded memory between waves
                        pacer.success()
                        controller.success(run)
                    except ProviderHydrationError as exc:
                        if exc.http_status == 429:
                            pacer.rate_limited(exc.retry_after)
                            controller.rate_limited(run)
                            quota_guard.rate_limited(
                                run,
                                retry_after=exc.retry_after,
                                reason=exc.reason,
                            )
                        elif exc.http_status is not None and exc.http_status >= 500:
                            quota_guard.refund_request(
                                run, charged_weight=settings.SPOTIFY_HYDRATION_SERVER_ERROR_WEIGHT,
                            )
                            controller.server_error(run)
                        elif not exc.retryable:
                            self.stderr.write(str(exc))
                    if controller.adaptive:
                        pacer.set_rate(controller.rps(run))
                    self._metrics(run, options['metrics_path'])
            except Exception as exc:
                if run is not None:
                    run.status = 'failed'
                    run.last_error = str(exc)
                    run.completed_at = timezone.now()
                    run.save()
                    self._metrics(run, options['metrics_path'])
                raise
            else:
                run.status = 'succeeded'
                run.completed_at = timezone.now()
                run.metadata = {**run.metadata, 'final_rps': pacer.current_rps}
                run.save()
                self._metrics(run, options['metrics_path'])
        self._output(self._payload(run, seeded), options)

    @staticmethod
    def _validate(options):
        if options['rps'] <= 0:
            raise CommandError('--rps must be greater than zero.')
        for option in (
            'seed_limit',
            'max_items',
            'batch_size',
            'incremental_seed_scan_limit',
            'priority_rescore_batch_size',
            'wave_max_seeds',
            'wave_fan_out',
            'wave_max_updates',
        ):
            if options.get(option) is not None and options[option] < 1:
                raise CommandError(f'--{option.replace("_", "-")} must be greater than zero.')
        for option in (
            'database_wait_timeout_seconds',
            'database_wait_interval_seconds',
            'incremental_seed_interval_seconds',
            'idle_sleep_seconds',
            'priority_rescore_interval_seconds',
            'priority_boost_interval_seconds',
            'wave_interval_seconds',
            'wave_time_budget_seconds',
        ):
            if options[option] <= 0:
                raise CommandError(f'--{option.replace("_", "-")} must be greater than zero.')
        if options['seed_only'] and options['skip_seed']:
            raise CommandError('--seed-only and --skip-seed cannot be combined.')

    @staticmethod
    def _incremental_seed(run, options):
        result = seed_spotify_hydration_queue_incrementally(
            after_source_id=run.metadata.get('incremental_seed_cursor', ''),
            scan_limit=options['incremental_seed_scan_limit'],
        )
        run.metadata = {
            **run.metadata,
            'incremental_seed_cursor': result.next_cursor,
            'incremental_seed_scanned_total': (
                run.metadata.get('incremental_seed_scanned_total', 0) + result.scanned
            ),
            'incremental_seed_created_total': (
                run.metadata.get('incremental_seed_created_total', 0) + result.created
            ),
            'incremental_seed_passes_completed': (
                run.metadata.get('incremental_seed_passes_completed', 0)
                + int(result.pass_complete)
            ),
            'incremental_seed_last_at': timezone.now().isoformat(),
        }
        run.save(update_fields=['metadata', 'updated_at'])
        return result.created

    @staticmethod
    def _wave(run, options, seeds):
        result = expand_wave(
            seeds,
            max_seeds=options['wave_max_seeds'],
            fan_out=options['wave_fan_out'],
            sibling_fan_out=options['wave_sibling_fan_out'],
            max_updates=options['wave_max_updates'],
            time_budget_seconds=options['wave_time_budget_seconds'],
        )
        meta = run.metadata
        run.metadata = {
            **meta,
            'wave_count': meta.get('wave_count', 0) + 1,
            'wave_seeds_total': meta.get('wave_seeds_total', 0) + result.seeds_used,
            'wave_neighbors_total': meta.get('wave_neighbors_total', 0) + result.neighbors,
            'wave_rows_updated_total': meta.get('wave_rows_updated_total', 0) + result.rows_updated,
            'wave_last_at': timezone.now().isoformat(),
        }
        run.save(update_fields=['metadata', 'updated_at'])
        return result.remaining_seeds

    def _refresh_boosts(self, run, options):
        """Recompute the user-referenced boosts (small tables) and write them onto pending rows."""
        if options['skip_priority_boost']:
            return
        now = time.monotonic()
        last = getattr(self, '_boosts_at', None)
        if last is not None and now - last < options['priority_boost_interval_seconds']:
            return
        self._boosts = referenced_canonical_priorities()
        self._boosts_at = now
        boosted = apply_referenced_boosts(self._boosts)
        run.metadata = {
            **run.metadata,
            'priority_boost_items': len(self._boosts),
            'priority_boost_rows_updated_total': run.metadata.get('priority_boost_rows_updated_total', 0) + boosted,
            'priority_boost_last_at': timezone.now().isoformat(),
        }
        run.save(update_fields=['metadata', 'updated_at'])

    def _priority_rescore(self, run, options):
        self._refresh_boosts(run, options)
        result = rescore_pending_priorities(
            after_id=run.metadata.get('priority_rescore_cursor', 0),
            batch_size=options['priority_rescore_batch_size'],
            boosts=getattr(self, '_boosts', None),
        )
        run.metadata = {
            **run.metadata,
            'priority_rescore_cursor': result.next_cursor,
            'priority_rescore_scanned_total': run.metadata.get('priority_rescore_scanned_total', 0) + result.scanned,
            'priority_rescore_updated_total': run.metadata.get('priority_rescore_updated_total', 0) + result.updated,
            'priority_rescore_passes_completed': (
                run.metadata.get('priority_rescore_passes_completed', 0) + int(result.pass_complete)
            ),
            'priority_rescore_last_at': timezone.now().isoformat(),
        }
        run.save(update_fields=['metadata', 'updated_at'])

    @staticmethod
    def _metrics(run, path):
        if path:
            write_hydration_metrics(run, path=path)

    def _output(self, payload, options):
        if options['json']:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        else:
            self.stdout.write(' '.join(f'{key}={value}' for key, value in payload.items()))

    @staticmethod
    def _payload(run, seeded):
        elapsed = max((run.completed_at - run.started_at).total_seconds(), 0.001)
        backlog = ProviderHydrationItem.objects.filter(
            provider='spotify', status__in=['pending', 'retry', 'running'],
        ).count()
        throughput = run.attempted_count / elapsed
        return {
            'run_id': str(run.id),
            'status': run.status,
            'seeded': seeded,
            'attempted': run.attempted_count,
            'matched': run.matched_count,
            'no_match': run.no_match_count,
            'ambiguous': run.ambiguous_count,
            'retries': run.retry_count,
            'rate_limited': run.rate_limited_count,
            'dead': run.dead_count,
            'throughput_per_second': round(throughput, 6),
            'backlog': backlog,
            'eta_seconds_at_observed_rate': round(backlog / throughput, 1) if throughput else None,
        }
