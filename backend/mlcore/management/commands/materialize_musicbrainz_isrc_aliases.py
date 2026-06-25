import json
import os
import time
from uuid import UUID

from django.core.management.base import BaseCommand
from django.utils import timezone

from mlcore.models import CanonicalAliasMaterializationRun
from mlcore.services.canonical_items import AliasMaterializationProgress, write_alias_materialization_metrics
from mlcore.services.musicbrainz_isrc_aliases import (
    ALGORITHM_VERSION,
    count_musicbrainz_isrcs,
    latest_musicbrainz_isrc_source_version,
    materialize_musicbrainz_isrc_alias_batch,
)


DEFAULT_METRICS_PATH = '/srv/monitoring/node-exporter/textfile/mlcore_canonical_alias_materialization.prom'


class Command(BaseCommand):
    help = 'Materialize unambiguous MusicBrainz ISRC evidence directly into canonical aliases.'

    def add_arguments(self, parser):
        parser.add_argument('--source-version', help='MusicBrainz bridge source version; defaults to latest successful.')
        parser.add_argument('--batch-size', type=int, default=100_000)
        parser.add_argument('--max-batches', type=int)
        parser.add_argument('--resume-run-id', type=UUID)
        parser.add_argument('--json', action='store_true')
        parser.add_argument(
            '--metrics-path',
            default=os.environ.get('MLCORE_CANONICAL_ALIAS_TEXTFILE_METRICS_PATH', DEFAULT_METRICS_PATH),
        )

    def handle(self, *args, **options):
        if options['batch_size'] < 1:
            raise ValueError('batch_size must be greater than zero')
        if options.get('max_batches') is not None and options['max_batches'] < 1:
            raise ValueError('max_batches must be greater than zero')

        run = self._get_or_create_run(options)
        metrics_path = str(options.get('metrics_path') or '').strip() or None
        batch_count = 0
        try:
            while True:
                checkpoint = dict(run.checkpoints or {})
                result = materialize_musicbrainz_isrc_alias_batch(
                    source_version=run.source_version,
                    last_isrc=checkpoint.get('last_isrc'),
                    batch_size=run.batch_size,
                )
                if result.processed_count == 0:
                    run.status = 'succeeded'
                    run.current_phase = 'complete'
                    run.completed_at = timezone.now()
                    run.last_error = ''
                    run.save()
                    self._write_metrics(run, metrics_path)
                    break

                batch_count += 1
                run.processed_items += result.processed_count
                run.created_count += result.created_count
                run.existing_count += result.existing_count
                run.conflict_count += result.ambiguous_count + result.existing_alias_conflict_count
                run.batches_processed += 1
                run.current_phase = 'musicbrainz_isrc'
                run.checkpoints = {
                    **checkpoint,
                    'last_isrc': result.last_isrc,
                    'ambiguous_count': int(checkpoint.get('ambiguous_count') or 0) + result.ambiguous_count,
                    'unresolved_count': int(checkpoint.get('unresolved_count') or 0) + result.unresolved_count,
                    'existing_alias_conflict_count': (
                        int(checkpoint.get('existing_alias_conflict_count') or 0)
                        + result.existing_alias_conflict_count
                    ),
                }
                run.save()
                self._write_metrics(run, metrics_path)
                self.stderr.write(
                    'phase=musicbrainz_isrc '
                    f'processed={run.processed_items}/{run.total_items} '
                    f'created={run.created_count} existing={run.existing_count} '
                    f'conflicts={run.conflict_count} last_isrc={result.last_isrc}'
                )
                if options.get('max_batches') and batch_count >= options['max_batches']:
                    run.status = 'pending'
                    run.current_phase = 'paused'
                    run.save(update_fields=['status', 'current_phase', 'updated_at'])
                    self._write_metrics(run, metrics_path)
                    break
        except Exception as exc:
            run.status = 'failed'
            run.last_error = str(exc)
            run.save(update_fields=['status', 'last_error', 'updated_at'])
            self._write_metrics(run, metrics_path)
            raise

        payload = {
            'run_id': str(run.id),
            'source_version': run.source_version,
            'status': run.status,
            'total_isrcs': run.total_items,
            'processed_isrcs': run.processed_items,
            'created_aliases': run.created_count,
            'existing_aliases': run.existing_count,
            'conflicts': run.conflict_count,
            'ambiguous_isrcs': int(run.checkpoints.get('ambiguous_count') or 0),
            'unresolved_isrcs': int(run.checkpoints.get('unresolved_count') or 0),
            'existing_alias_conflicts': int(run.checkpoints.get('existing_alias_conflict_count') or 0),
        }
        if options['json']:
            self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        else:
            self.stdout.write(' '.join(f'{key}={value}' for key, value in payload.items()))

    def _get_or_create_run(self, options):
        if options.get('resume_run_id'):
            run = CanonicalAliasMaterializationRun.objects.get(pk=options['resume_run_id'])
            if run.algorithm_version != ALGORITHM_VERSION:
                raise ValueError(f'Run {run.id} uses incompatible algorithm {run.algorithm_version}.')
            if run.status == 'succeeded':
                raise ValueError(f'Run {run.id} has already succeeded.')
            run.status = 'running'
            run.current_phase = 'musicbrainz_isrc'
            run.last_error = ''
            run.completed_at = None
            run.save()
            return run

        source_version = options.get('source_version') or latest_musicbrainz_isrc_source_version()
        return CanonicalAliasMaterializationRun.objects.create(
            source_version=source_version,
            algorithm_version=ALGORITHM_VERSION,
            status='running',
            current_phase='musicbrainz_isrc',
            batch_size=options['batch_size'],
            total_items=count_musicbrainz_isrcs(source_version),
        )

    @staticmethod
    def _write_metrics(run, metrics_path):
        if metrics_path is None:
            return
        elapsed = max(0.0, (timezone.now() - run.started_at).total_seconds())
        write_alias_materialization_metrics(
            AliasMaterializationProgress(
                status=run.status,
                total_items=run.total_items,
                processed_items=run.processed_items,
                created_count=run.created_count,
                existing_count=run.existing_count,
                conflict_count=run.conflict_count,
                batch_size=run.batch_size,
                batches_processed=run.batches_processed,
                wall_started_at=run.started_at,
                monotonic_started_at=time.monotonic() - elapsed,
                source_version=run.source_version,
                phase=run.current_phase,
                run_id=run.id,
                algorithm_version=run.algorithm_version,
            ),
            metrics_path=metrics_path,
        )
