import json
import tempfile
from dataclasses import replace
from pathlib import Path

from django.test import TestCase, override_settings

from mlcore.models import SourceIngestionRun
from mlcore.services.dataset_orchestration import (
    DatasetOrchestrationDocument,
    configured_celery_worker_total_slots,
    configured_dataset_shard_parallelism,
    dispatch_dataset_shard_tasks,
    ensure_dataset_shard_runs,
    expire_stale_dataset_shard_runs,
    get_or_create_dataset_orchestration_run,
    load_dataset_orchestration_document,
    refresh_dataset_orchestration_run,
    validate_dataset_worker_capacity,
)
from mlcore.tasks import import_dataset_shard_task


class _DispatchResult:
    def __init__(self, task_id: str):
        self.id = task_id


@override_settings(
    MLCORE_DATASET_ORCHESTRATION_POLL_SECONDS=0.01,
)
class DatasetOrchestrationTests(TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.output_root = self.temp_dir / 'listenbrainz-dump-2446-20260301-000003-full'
        (self.output_root / 'listens/2007').mkdir(parents=True, exist_ok=True)
        (self.output_root / 'listens/2007/5.listens').write_text(
            '\n'.join(
                [
                    json.dumps(
                        {
                            'user_name': 'alice',
                            'listened_at': 1710000000,
                            'track_metadata': {
                                'track_name': 'Song One',
                                'artist_name': 'Artist',
                                'release_name': 'Album',
                                'recording_msid': 'msid-1',
                                'additional_info': {},
                            },
                        }
                    )
                ]
            )
            + '\n',
            encoding='utf-8',
        )
        (self.output_root / 'listens/2007/6.listens').write_text(
            '\n'.join(
                [
                    json.dumps(
                        {
                            'user_name': 'bob',
                            'listened_at': 1710000060,
                            'track_metadata': {
                                'track_name': 'Song Two',
                                'artist_name': 'Artist',
                                'release_name': 'Album',
                                'recording_msid': 'msid-2',
                                'additional_info': {},
                            },
                        }
                    )
                ]
            )
            + '\n',
            encoding='utf-8',
        )
        self.manifest_path = self.output_root / 'manifest.json'
        self.orchestration_path = self.output_root / 'orchestration.json'
        self.manifest_path.write_text(
            json.dumps(
                {
                    'source': 'listenbrainz',
                    'source_version': 'listenbrainz-dump-2446-20260301-000003-full',
                    'shard_count': 2,
                    'total_uncompressed_bytes': 2,
                    'shards': [
                        {
                            'relative_path': 'listens/2007/5.listens',
                            'size_bytes': 1,
                            'year': 2007,
                            'month': 5,
                        },
                        {
                            'relative_path': 'listens/2007/6.listens',
                            'size_bytes': 1,
                            'year': 2007,
                            'month': 6,
                        },
                    ],
                }
            ),
            encoding='utf-8',
        )
        self.orchestration_path.write_text(
            json.dumps(
                {
                    'provider': 'listenbrainz',
                    'source_version': 'listenbrainz-dump-2446-20260301-000003-full',
                    'manifest_path': str(self.manifest_path),
                    'output_root': str(self.output_root),
                    'orchestration_path': str(self.orchestration_path),
                    'shard_parallelism': 1,
                    'max_shards_per_run': None,
                    'shard_count': 2,
                    'scheduled_shard_count': 2,
                    'total_uncompressed_bytes': 2,
                    'scheduled_uncompressed_bytes': 2,
                    'shards': [
                        {
                            'relative_path': 'listens/2007/5.listens',
                            'size_bytes': 1,
                            'year': 2007,
                            'month': 5,
                        },
                        {
                            'relative_path': 'listens/2007/6.listens',
                            'size_bytes': 1,
                            'year': 2007,
                            'month': 6,
                        },
                    ],
                }
            ),
            encoding='utf-8',
        )

    def _document(self) -> DatasetOrchestrationDocument:
        return load_dataset_orchestration_document(self.orchestration_path)

    def test_dispatch_respects_parallel_worker_limit(self):
        document = self._document()
        orchestration_run = get_or_create_dataset_orchestration_run(document)
        ensure_dataset_shard_runs(orchestration_run, document)

        dispatched = dispatch_dataset_shard_tasks(
            orchestration_run,
            document,
            orchestration_session_id='session-1',
            dispatch_shard_task=lambda provider, orchestration_run_id, shard_run_id: _DispatchResult(shard_run_id),
        )

        self.assertEqual(len(dispatched), 1)
        self.assertEqual(
            orchestration_run.shard_runs.filter(status='running').count(),
            1,
        )
        self.assertEqual(
            orchestration_run.shard_runs.filter(status='pending').count(),
            1,
        )

    def test_stale_running_shard_marks_source_run_failed_and_requeues(self):
        document = self._document()
        orchestration_run = get_or_create_dataset_orchestration_run(document)
        ensure_dataset_shard_runs(orchestration_run, document)
        shard_run = orchestration_run.shard_runs.get(shard_key='listens/2007/5.listens')
        source_run = SourceIngestionRun.objects.create(
            source='listenbrainz',
            import_mode='full',
            source_version=document.plan.source_version,
            raw_path=shard_run.shard_path,
            checksum='checksum',
            status='running',
            metadata={'last_progress_at': '2000-01-01T00:00:00+00:00'},
        )
        shard_run.status = 'running'
        shard_run.source_ingestion_run = source_run
        shard_run.metadata = {
            **shard_run.metadata,
            'orchestrator_session_id': 'session-1',
            'last_progress_at': '2000-01-01T00:00:00+00:00',
        }
        shard_run.save(update_fields=['status', 'source_ingestion_run', 'metadata'])

        stale_runs = expire_stale_dataset_shard_runs(orchestration_run)

        self.assertEqual(len(stale_runs), 1)
        shard_run.refresh_from_db()
        source_run.refresh_from_db()
        self.assertEqual(shard_run.status, 'failed')
        self.assertEqual(source_run.status, 'failed')
        self.assertTrue(shard_run.metadata.get('stale_marked_at'))

        dispatched = dispatch_dataset_shard_tasks(
            orchestration_run,
            document,
            orchestration_session_id='session-1',
            dispatch_shard_task=lambda provider, orchestration_run_id, shard_run_id: _DispatchResult('retry-task'),
        )
        self.assertEqual(len(dispatched), 1)
        shard_run.refresh_from_db()
        self.assertEqual(shard_run.status, 'running')
        self.assertEqual(shard_run.task_id, 'retry-task')
        self.assertNotIn('stale_marked_at', shard_run.metadata)

    def test_ensure_dataset_shard_runs_removes_obsolete_rows_after_schedule_change(self):
        document = self._document()
        orchestration_run = get_or_create_dataset_orchestration_run(document)
        ensure_dataset_shard_runs(orchestration_run, document)
        self.assertEqual(orchestration_run.shard_runs.count(), 2)

        reduced_document = DatasetOrchestrationDocument(
            plan=replace(
                document.plan,
                max_shards_per_run=1,
                scheduled_shard_count=1,
                scheduled_uncompressed_bytes=1,
            ),
            shards=[document.shards[0]],
        )

        ensure_dataset_shard_runs(orchestration_run, reduced_document)

        self.assertEqual(
            list(orchestration_run.shard_runs.values_list('shard_key', flat=True)),
            ['listens/2007/5.listens'],
        )

    def test_import_dataset_shard_task_updates_shard_run_and_links_source_run(self):
        document = self._document()
        orchestration_run = get_or_create_dataset_orchestration_run(document)
        ensure_dataset_shard_runs(orchestration_run, document)
        shard_run = orchestration_run.shard_runs.get(shard_key='listens/2007/5.listens')

        async_result = import_dataset_shard_task.apply(
            kwargs={
                'provider': 'listenbrainz',
                'orchestration_run_id': str(orchestration_run.pk),
                'shard_run_id': str(shard_run.pk),
            }
        )
        result = async_result.get()

        shard_run.refresh_from_db()
        self.assertEqual(result['status'], 'succeeded')
        self.assertEqual(shard_run.status, 'succeeded')
        self.assertTrue(shard_run.source_ingestion_run_id)
        self.assertEqual(shard_run.imported_row_count, 1)
        self.assertEqual(
            SourceIngestionRun.objects.get(pk=shard_run.source_ingestion_run_id).status,
            'succeeded',
        )

    def test_refresh_aggregates_shard_progress_into_orchestration_run(self):
        document = self._document()
        orchestration_run = get_or_create_dataset_orchestration_run(document)
        ensure_dataset_shard_runs(orchestration_run, document)
        shard_runs = list(orchestration_run.shard_runs.order_by('shard_key'))
        shard_runs[0].status = 'succeeded'
        shard_runs[0].source_row_count = 10
        shard_runs[0].imported_row_count = 8
        shard_runs[0].duplicate_row_count = 2
        shard_runs[0].metadata = {**shard_runs[0].metadata, 'size_bytes': 11}
        shard_runs[0].save(update_fields=['status', 'source_row_count', 'imported_row_count', 'duplicate_row_count', 'metadata'])
        shard_runs[1].status = 'running'
        shard_runs[1].source_row_count = 4
        shard_runs[1].imported_row_count = 4
        shard_runs[1].metadata = {**shard_runs[1].metadata, 'size_bytes': 7}
        shard_runs[1].save(update_fields=['status', 'source_row_count', 'imported_row_count', 'metadata'])

        aggregate = refresh_dataset_orchestration_run(orchestration_run, document)

        orchestration_run.refresh_from_db()
        self.assertEqual(aggregate['completed_shards'], 1)
        self.assertEqual(aggregate['running_shards'], 1)
        self.assertEqual(aggregate['completed_uncompressed_bytes'], 11)
        self.assertEqual(aggregate['source_row_count'], 14)
        self.assertEqual(orchestration_run.source_row_count, 14)

    @override_settings(
        MLCORE_DATASET_SHARD_PARALLELISM=2,
        CELERY_WORKER_TOTAL_SLOTS=3,
    )
    def test_worker_capacity_validation_accepts_one_orchestrator_plus_shards(self):
        self.assertEqual(configured_dataset_shard_parallelism(), 2)
        self.assertEqual(configured_celery_worker_total_slots(), 3)
        self.assertEqual(validate_dataset_worker_capacity(), 2)

    @override_settings(
        MLCORE_DATASET_SHARD_PARALLELISM=2,
        CELERY_WORKER_TOTAL_SLOTS=2,
    )
    def test_worker_capacity_validation_requires_extra_slot_for_orchestrator(self):
        with self.assertRaisesMessage(ValueError, 'CELERY_WORKER_TOTAL_SLOTS >= MLCORE_DATASET_SHARD_PARALLELISM + 1'):
            validate_dataset_worker_capacity()
