import json

from django.core.management.base import BaseCommand

from mlcore.services.identity_coverage import (
    DEFAULT_METRICS_PATH,
    compute_play_weighted_coverage,
    write_coverage_metrics,
)


class Command(BaseCommand):
    help = (
        'Compute play-weighted MBID / ISRC / Spotify coverage (set-based) and write it to the '
        'node_exporter textfile collector. Heavy on the full corpus: schedule rarely, or use --sample-percent.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--metrics-path', default=DEFAULT_METRICS_PATH, help='Prometheus textfile to write.')
        parser.add_argument('--sample-percent', type=float, default=100.0,
                            help='TABLESAMPLE SYSTEM percentage of the session table to scan (ratios stay unbiased).')
        parser.add_argument('--staging-tablespace', help='temp_tablespaces for the staging tables, e.g. the NVMe one.')
        parser.add_argument('--json', action='store_true', help='Emit the result as JSON instead of text.')

    def handle(self, *args, **options):
        coverage = compute_play_weighted_coverage(
            sample_percent=options['sample_percent'],
            staging_tablespace=options.get('staging_tablespace'),
            progress_callback=lambda message: self.stderr.write(f'event=coverage {message}'),
        )
        path = write_coverage_metrics(coverage, options['metrics_path'])
        payload = {
            'sample_percent': coverage.sample_percent,
            'total_plays': coverage.total_plays,
            'total_items': coverage.total_items,
            'unresolved_plays': coverage.unresolved_plays,
            'play_coverage': {s: round(coverage.play_ratio(s), 6) for s in ('mbid', 'isrc', 'spotify')},
            'item_coverage': {s: round(coverage.item_ratio(s), 6) for s in ('mbid', 'isrc', 'spotify')},
            'elapsed_seconds': round(coverage.elapsed_seconds, 3),
            'metrics_path': str(path),
        }
        if options['json']:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
            return
        self.stdout.write(' '.join(f'{key}={value}' for key, value in payload.items()))
