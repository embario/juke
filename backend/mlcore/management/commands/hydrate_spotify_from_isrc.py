import json
import os

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from mlcore.models import ProviderHydrationItem, ProviderHydrationRun
from mlcore.services.provider_hydration import (
    ProviderHydrationError,
    RequestPacer,
    SpotifyClient,
    claim_hydration_item,
    hydrate_spotify_item,
    seed_spotify_hydration_queue,
    spotify_worker_lock,
    worker_identity,
    write_hydration_metrics,
)


DEFAULT_METRICS_PATH = '/srv/monitoring/node-exporter/textfile/mlcore_provider_hydration.prom'


class Command(BaseCommand):
    help = 'Seed and process the durable Spotify-from-ISRC identity hydration queue.'

    def add_arguments(self, parser):
        parser.add_argument('--seed-only', action='store_true')
        parser.add_argument('--skip-seed', action='store_true')
        parser.add_argument('--seed-limit', type=int)
        parser.add_argument('--max-items', type=int)
        parser.add_argument('--rps', type=float, default=settings.SPOTIFY_HYDRATION_INITIAL_RPS)
        parser.add_argument('--batch-size', type=int, default=10_000)
        parser.add_argument('--json', action='store_true')
        parser.add_argument(
            '--metrics-path',
            default=os.environ.get('MLCORE_PROVIDER_HYDRATION_METRICS_PATH', DEFAULT_METRICS_PATH),
        )

    def handle(self, *args, **options):
        self._validate(options)
        seeded = 0
        if not options['skip_seed']:
            seeded = seed_spotify_hydration_queue(
                batch_size=options['batch_size'],
                limit=options['seed_limit'],
            )
        if options['seed_only']:
            self._output({'seeded': seeded, 'status': 'seeded'}, options)
            return

        client = SpotifyClient(
            settings.SPOTIFY_HYDRATION_CLIENT_ID,
            settings.SPOTIFY_HYDRATION_CLIENT_SECRET,
        )
        run = ProviderHydrationRun.objects.create(
            provider='spotify',
            requested_limit=options['max_items'],
            configured_rps=options['rps'],
            metadata={'seeded_at_start': seeded},
        )
        pacer = RequestPacer(options['rps'])
        worker_id = worker_identity()
        try:
            with spotify_worker_lock() as acquired:
                if not acquired:
                    raise CommandError('Another Spotify hydration worker already owns the global provider lease.')
                while options['max_items'] is None or run.attempted_count < options['max_items']:
                    item = claim_hydration_item(run=run, worker_id=worker_id)
                    if item is None:
                        break
                    pacer.wait()
                    try:
                        hydrate_spotify_item(item, run=run, client=client)
                        pacer.success()
                    except ProviderHydrationError as exc:
                        if exc.http_status == 429:
                            pacer.rate_limited(exc.retry_after)
                        elif not exc.retryable:
                            self.stderr.write(str(exc))
                    self._metrics(run, options['metrics_path'])
            run.status = 'succeeded'
            run.completed_at = timezone.now()
            run.metadata = {**run.metadata, 'final_rps': pacer.current_rps}
            run.save()
        except Exception as exc:
            run.status = 'failed'
            run.last_error = str(exc)
            run.completed_at = timezone.now()
            run.save()
            self._metrics(run, options['metrics_path'])
            raise
        self._metrics(run, options['metrics_path'])
        self._output(self._payload(run, seeded), options)

    @staticmethod
    def _validate(options):
        if options['rps'] <= 0:
            raise CommandError('--rps must be greater than zero.')
        for option in ('seed_limit', 'max_items', 'batch_size'):
            if options.get(option) is not None and options[option] < 1:
                raise CommandError(f'--{option.replace("_", "-")} must be greater than zero.')
        if options['seed_only'] and options['skip_seed']:
            raise CommandError('--seed-only and --skip-seed cannot be combined.')

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
