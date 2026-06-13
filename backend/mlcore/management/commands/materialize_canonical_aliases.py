import os
from pathlib import Path
import time
from uuid import UUID

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from catalog.models import Track
from mlcore.models import CanonicalAliasMaterializationRun
from mlcore.services.canonical_items import (
    AliasMaterializationProgress,
    CANONICAL_ALIAS_SOURCE_MAPPINGS,
    count_canonical_alias_source_items,
    materialize_canonical_item_self_aliases,
    materialize_track_aliases,
    merge_alias_materialization_results,
    write_alias_materialization_metrics,
)


DEFAULT_METRICS_PATH = '/srv/monitoring/node-exporter/textfile/mlcore_canonical_alias_materialization.prom'


class Command(BaseCommand):
    help = 'Materialize MLCore canonical item aliases from shared catalog track identifiers.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--source-version',
            default='',
            help='Optional source/corpus version label to stamp on newly-created aliases.',
        )
        parser.add_argument(
            '--batch-size',
            type=int,
            default=100_000,
            help='Number of source items to process per batch.',
        )
        parser.add_argument(
            '--include-catalog-tracks',
            action='store_true',
            help='Also materialize aliases from local catalog tracks and TrackExternalIdentifier rows.',
        )
        parser.add_argument(
            '--metrics-path',
            default=os.environ.get('MLCORE_CANONICAL_ALIAS_TEXTFILE_METRICS_PATH', DEFAULT_METRICS_PATH),
            help='Prometheus textfile path for canonical alias materialization progress metrics.',
        )
        parser.add_argument(
            '--resume-run-id',
            type=UUID,
            help='Resume a failed or interrupted materialization run from its persisted checkpoints.',
        )

    def handle(self, *args, **options):
        metrics_path = str(options['metrics_path'] or '').strip() or None
        run = self._get_or_create_run(options)

        def metrics_progress():
            elapsed = max(0.0, (timezone.now() - run.started_at).total_seconds())
            progress = AliasMaterializationProgress(
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
            )
            write_alias_materialization_metrics(progress, metrics_path=metrics_path)

        result = None

        try:
            result = self._materialize_canonical_phase(run, metrics_progress)
            if run.include_catalog_tracks:
                result = merge_alias_materialization_results(
                    result,
                    self._materialize_catalog_phase(run, metrics_progress),
                )
        except Exception as exc:
            run.status = 'failed'
            run.last_error = str(exc)
            run.save(update_fields=['status', 'last_error', 'updated_at'])
            metrics_progress()
            raise

        run.status = 'succeeded'
        run.current_phase = 'complete'
        run.completed_at = timezone.now()
        run.last_error = ''
        run.save(update_fields=['status', 'current_phase', 'completed_at', 'last_error', 'updated_at'])
        metrics_progress()
        result = self._result_from_run(run)

        if metrics_path is not None:
            self.stdout.write(f'wrote metrics={Path(metrics_path)}')
        self.stdout.write(f'materialization_run_id={run.id}')
        self.stdout.write(
            self.style.SUCCESS(
                'canonical aliases materialized: '
                f'created={result.created_count} existing={result.existing_count} '
                f'conflicts={result.conflict_count}'
            )
        )
        for conflict in result.conflicts[:20]:
            self.stdout.write(
                self.style.WARNING(
                    'conflict '
                    f'{conflict.source}:{conflict.resource_type}:{conflict.source_id} '
                    f'existing={conflict.existing_canonical_item_id} '
                    f'desired={conflict.desired_canonical_item_id} '
                    f'reason={conflict.reason}'
                )
            )
        if result.conflict_count > 20:
            self.stdout.write(self.style.WARNING(f'... {result.conflict_count - 20} more conflicts omitted'))

    def _get_or_create_run(self, options):
        resume_run_id = options.get('resume_run_id')
        if resume_run_id:
            run = CanonicalAliasMaterializationRun.objects.get(pk=resume_run_id)
            if run.status == 'succeeded':
                raise ValueError(f'Materialization run {run.id} has already succeeded.')
            run.status = 'running'
            run.last_error = ''
            run.completed_at = None
            run.save(update_fields=['status', 'last_error', 'completed_at', 'updated_at'])
            return run

        total_items = count_canonical_alias_source_items(CANONICAL_ALIAS_SOURCE_MAPPINGS)
        if options['include_catalog_tracks']:
            total_items += Track.objects.count()
        source_version = options['source_version'] or timezone.now().strftime('canonical-alias-%Y%m%dT%H%M%SZ')
        return CanonicalAliasMaterializationRun.objects.create(
            source_version=source_version,
            status='running',
            include_catalog_tracks=options['include_catalog_tracks'],
            batch_size=options['batch_size'],
            total_items=total_items,
        )

    def _materialize_canonical_phase(self, run, metrics_progress):
        checkpoints = dict(run.checkpoints or {})
        if checkpoints.get('canonical_complete'):
            return self._empty_result()

        base = self._counter_snapshot(run)

        def checkpoint(mapping, last_id, progress):
            with transaction.atomic():
                run.checkpoints = {
                    **(run.checkpoints or {}),
                    'canonical': {
                        **(run.checkpoints or {}).get('canonical', {}),
                        mapping.item_type: str(last_id),
                    },
                }
                self._apply_phase_progress(run, progress, base, phase=progress.phase)
                run.save()

        materialized = materialize_canonical_item_self_aliases(
            source_version=run.source_version,
            batch_size=run.batch_size,
            progress_callback=lambda progress: metrics_progress(),
            start_after_by_item_type=checkpoints.get('canonical', {}),
            checkpoint_callback=checkpoint,
        )
        run.checkpoints = {**(run.checkpoints or {}), 'canonical_complete': True}
        run.save(update_fields=['checkpoints', 'updated_at'])
        return materialized

    def _materialize_catalog_phase(self, run, metrics_progress):
        checkpoints = dict(run.checkpoints or {})
        if checkpoints.get('catalog_complete'):
            return self._empty_result()

        base = self._counter_snapshot(run)

        def checkpoint(last_track_id, progress):
            with transaction.atomic():
                run.checkpoints = {
                    **(run.checkpoints or {}),
                    'catalog_last_id': str(last_track_id),
                }
                self._apply_phase_progress(run, progress, base, phase='catalog_tracks')
                run.save()

        materialized = materialize_track_aliases(
            source_version=run.source_version,
            batch_size=run.batch_size,
            progress_callback=lambda progress: metrics_progress(),
            start_after_track_id=checkpoints.get('catalog_last_id'),
            checkpoint_callback=checkpoint,
        )
        run.checkpoints = {**(run.checkpoints or {}), 'catalog_complete': True}
        run.save(update_fields=['checkpoints', 'updated_at'])
        return materialized

    @staticmethod
    def _counter_snapshot(run):
        return {
            'processed': run.processed_items,
            'created': run.created_count,
            'existing': run.existing_count,
            'conflicts': run.conflict_count,
            'batches': run.batches_processed,
        }

    @staticmethod
    def _apply_phase_progress(run, progress, base, *, phase):
        run.status = 'running'
        run.current_phase = phase
        run.processed_items = base['processed'] + progress.processed_items
        run.created_count = base['created'] + progress.created_count
        run.existing_count = base['existing'] + progress.existing_count
        run.conflict_count = base['conflicts'] + progress.conflict_count
        run.batches_processed = base['batches'] + progress.batches_processed

    @staticmethod
    def _result_from_run(run):
        from mlcore.services.canonical_items import AliasMaterializationResult

        return AliasMaterializationResult(
            created_count=run.created_count,
            existing_count=run.existing_count,
            conflict_count=run.conflict_count,
        )

    @staticmethod
    def _empty_result():
        from mlcore.services.canonical_items import AliasMaterializationResult

        return AliasMaterializationResult()
