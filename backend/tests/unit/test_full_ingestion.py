import json
import tarfile
import tempfile
from datetime import UTC, datetime, timedelta
from io import BytesIO, StringIO
from pathlib import Path

from django.core.management import call_command
from django.db import connection
from django.test import TransactionTestCase, override_settings

from catalog.models import Album, Track
from mlcore.models import (
    FullIngestionLease,
    ListenBrainzEventLedger,
    ListenBrainzSessionTrack,
    SourceIngestionRun,
)
from mlcore.services.full_ingestion import (
    FULL_INGESTION_POLICY_THROUGHPUT,
    LISTENBRAINZ_EVENT_LOAD_TABLE,
    LISTENBRAINZ_SESSION_LOAD_TABLE,
    build_full_ingestion_partition_estimates,
    build_full_ingestion_plan,
    execute_full_ingestion_copy_stage,
    execute_full_ingestion_merge_stage,
    execute_full_ingestion_partition_stage,
    execute_full_ingestion_pipeline,
    ensure_listenbrainz_load_tables,
    full_ingestion_copy_manifest_path,
    initialize_full_ingestion_plan,
    load_full_ingestion_plan,
    write_full_ingestion_metrics,
)
from mlcore.ingestion.listenbrainz import infer_source_version_from_path
from mlcore.services.listenbrainz_shards import materialize_listenbrainz_shards
from mlcore.services.listenbrainz_source import sync_listenbrainz_remote_dumps
from mlcore.tasks import import_listenbrainz_full_task, replay_listenbrainz_incremental_task


class FullIngestionMixin:
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())
        self.may_payload = self._build_listen_row(
            user_name='alice',
            listened_at=1,
            track_name='May Song',
            artist_name='May Artist',
            release_name='May Release',
            spotify_id='spotify-may',
        )
        self.june_payload = b''.join(
            [
                self._build_listen_row(
                    user_name='alice',
                    listened_at=2,
                    track_name='June Song 1',
                    artist_name='June Artist',
                    release_name='June Release',
                    spotify_id='spotify-june-1',
                ),
                self._build_listen_row(
                    user_name='alice',
                    listened_at=3,
                    track_name='June Song 2',
                    artist_name='June Artist',
                    release_name='June Release',
                    spotify_id='spotify-june-2',
                ),
            ]
        )

    def _build_archive(self, archive_name: str = 'listenbrainz-listens-dump-2446-20260301-000003-full.tar') -> Path:
        archive_path = self.temp_dir / archive_name
        with tarfile.open(archive_path, 'w') as archive:
            self._add_member(
                archive,
                'listenbrainz-listens-dump-2446-20260301-000003-full/listens/2007/5.listens',
                self.may_payload,
            )
            self._add_member(
                archive,
                'listenbrainz-listens-dump-2446-20260301-000003-full/listens/2007/6.listens',
                self.june_payload,
            )
        return archive_path

    def _add_member(self, archive: tarfile.TarFile, name: str, payload: bytes) -> None:
        info = tarfile.TarInfo(name=name)
        info.size = len(payload)
        archive.addfile(info, BytesIO(payload))

    def _build_listen_row(
        self,
        *,
        user_name: str,
        listened_at: int,
        track_name: str,
        artist_name: str,
        release_name: str,
        spotify_id: str,
    ) -> bytes:
        payload = {
            'user_name': user_name,
            'listened_at': listened_at,
            'track_metadata': {
                'track_name': track_name,
                'artist_name': artist_name,
                'release_name': release_name,
                'additional_info': {
                    'spotify_id': spotify_id,
                },
            },
        }
        return (json.dumps(payload, sort_keys=True) + '\n').encode('utf-8')


class FullIngestionPlanningTests(FullIngestionMixin, TransactionTestCase):
    def test_partition_estimates_hash_monthly_shards_into_fixed_partitions(self):
        archive_path = self._build_archive()
        shard_root = self.temp_dir / 'shards'
        materialized = materialize_listenbrainz_shards(archive_path, shard_root=shard_root)

        total_bytes, partitions = build_full_ingestion_partition_estimates(
            materialized.manifest_path,
            partition_count=4,
        )

        self.assertEqual(total_bytes, materialized.total_uncompressed_bytes)
        self.assertEqual(len(partitions), 4)
        self.assertEqual(
            sum(partition['estimated_input_bytes'] for partition in partitions),
            materialized.total_uncompressed_bytes,
        )
        self.assertEqual(
            sum(partition['estimated_shard_count'] for partition in partitions),
            materialized.shard_count,
        )

    def test_initialize_full_ingestion_plan_writes_manifest_and_metrics(self):
        archive_path = self._build_archive()
        metrics_path = self.temp_dir / 'monitoring/mlcore_full_ingestion.prom'
        plan = build_full_ingestion_plan(
            'listenbrainz',
            archive_path,
            scratch_root=self.temp_dir / 'scratch',
            partition_count=8,
            partition_workers=3,
            load_workers=2,
            merge_workers=1,
            metrics_path=metrics_path,
        )

        initialize_full_ingestion_plan(plan)

        manifest_path = Path(plan.manifest_path)
        self.assertTrue(manifest_path.exists())
        self.assertTrue(Path(plan.partition_root).exists())
        self.assertTrue(Path(plan.log_root).exists())
        self.assertTrue(metrics_path.exists())

        loaded = load_full_ingestion_plan(manifest_path)
        self.assertEqual(loaded.partition_count, 8)
        self.assertEqual(loaded.partition_workers, 3)
        self.assertEqual(loaded.load_workers, 2)
        self.assertEqual(loaded.merge_workers, 1)
        self.assertEqual(len(loaded.partitions), 8)

        metrics_text = metrics_path.read_text(encoding='utf-8')
        self.assertIn('mlcore_full_ingestion_active{provider="listenbrainz"', metrics_text)
        self.assertIn('mlcore_full_ingestion_partition_count{provider="listenbrainz"', metrics_text)
        self.assertIn('mlcore_full_ingestion_worker_config{provider="listenbrainz"', metrics_text)

    @override_settings(MLCORE_FULL_INGESTION_TARGET_CHUNK_ROWS=1)
    def test_extract_stage_writes_compact_event_chunks_and_partition_manifests(self):
        archive_path = self._build_archive()
        plan = build_full_ingestion_plan(
            'listenbrainz',
            archive_path,
            scratch_root=self.temp_dir / 'scratch',
            partition_count=4,
        )

        initialize_full_ingestion_plan(plan)
        extracted = execute_full_ingestion_partition_stage(plan)

        self.assertEqual(extracted.stage, 'partition')
        self.assertEqual(extracted.status, 'running')
        self.assertEqual(extracted.counters['artifacts_discovered'], 2)
        self.assertEqual(extracted.counters['artifacts_partitioned'], 2)
        self.assertEqual(extracted.counters['rows_parsed'], 3)
        self.assertEqual(extracted.counters['rows_with_mbid_candidate'], 0)
        self.assertEqual(extracted.counters['rows_with_spotify_candidate'], 3)
        self.assertEqual(extracted.counters['rows_with_no_candidate'], 0)
        self.assertEqual(extracted.counters['rows_resolved'], 3)
        self.assertEqual(extracted.counters['rows_resolved_by_spotify'], 3)
        self.assertEqual(extracted.counters['rows_unresolved'], 0)
        self.assertEqual(extracted.counters['rows_malformed'], 0)
        self.assertEqual(extracted.counters['chunks_written'], 3)
        self.assertGreaterEqual(extracted.counters['chunk_bytes_written'], 1)
        self.assertEqual(extracted.counters['spool_bytes_estimated'], 0)
        self.assertEqual(extracted.counters['spooled_members_in_flight'], 0)
        self.assertTrue(all(partition.state == 'partitioned' for partition in extracted.partitions))

        manifests = sorted(Path(extracted.partition_root).glob('p*/manifest.json'))
        self.assertEqual(len(manifests), 4)
        populated_manifest = next(
            payload
            for payload in (json.loads(path.read_text(encoding='utf-8')) for path in manifests)
            if payload['event_chunk_count'] > 0
        )
        self.assertIn('event_chunks', populated_manifest)
        self.assertEqual(populated_manifest['event_chunks'][0]['relative_path'].split('/')[0], 'events')

    @override_settings(
        MLCORE_FULL_INGESTION_PARTITION_COUNT=6,
        MLCORE_FULL_INGESTION_PARTITION_WORKERS=5,
        MLCORE_FULL_INGESTION_LOAD_WORKERS=2,
        MLCORE_FULL_INGESTION_MERGE_WORKERS=2,
    )
    def test_command_plans_and_resumes_full_ingestion_manifest(self):
        archive_path = self._build_archive(
            archive_name='listenbrainz-listens-dump-2550-20260401-000003-full.tar'
        )
        scratch_root = self.temp_dir / 'scratch'
        metrics_path = self.temp_dir / 'metrics/mlcore_full_ingestion.prom'
        output_buffer = StringIO()

        call_command(
            'ingest_dataset_full',
            '--provider',
            'listenbrainz',
            '--archive-path',
            str(archive_path),
            '--scratch-root',
            str(scratch_root),
            '--metrics-path',
            str(metrics_path),
            stdout=output_buffer,
        )

        planned_output = output_buffer.getvalue()
        self.assertIn('planned provider=listenbrainz', planned_output)

        output_buffer = StringIO()
        call_command(
            'ingest_dataset_full',
            '--provider',
            'listenbrainz',
            '--archive-path',
            str(archive_path),
            '--scratch-root',
            str(scratch_root),
            '--metrics-path',
            str(metrics_path),
            '--resume',
            stdout=output_buffer,
        )
        self.assertIn('resumed provider=listenbrainz', output_buffer.getvalue())

    def test_status_command_reads_manifest_summary(self):
        archive_path = self._build_archive()
        scratch_root = self.temp_dir / 'scratch'
        call_command(
            'ingest_dataset_full',
            '--provider',
            'listenbrainz',
            '--archive-path',
            str(archive_path),
            '--scratch-root',
            str(scratch_root),
            '--partition-count',
            '4',
            '--execute-partition-stage',
        )

        output_buffer = StringIO()
        call_command(
            'ingest_dataset_status',
            '--provider',
            'listenbrainz',
            '--archive-path',
            str(archive_path),
            '--scratch-root',
            str(scratch_root),
            stdout=output_buffer,
        )
        output = output_buffer.getvalue()
        self.assertIn('provider=listenbrainz', output)
        self.assertIn('stage=partition', output)
        self.assertIn('rows_parsed=3', output)
        self.assertIn('candidates=mbid:0,spotify:3,none:0', output)
        self.assertIn('chunks_written=', output)

    def test_control_command_switches_policy_and_budgets(self):
        archive_path = self._build_archive()
        scratch_root = self.temp_dir / 'scratch'
        call_command(
            'ingest_dataset_full',
            '--provider',
            'listenbrainz',
            '--archive-path',
            str(archive_path),
            '--scratch-root',
            str(scratch_root),
            '--partition-count',
            '4',
        )

        output_buffer = StringIO()
        call_command(
            'ingest_dataset_control',
            '--provider',
            'listenbrainz',
            '--archive-path',
            str(archive_path),
            '--scratch-root',
            str(scratch_root),
            '--policy',
            FULL_INGESTION_POLICY_THROUGHPUT,
            '--partition-budget',
            '4',
            '--load-budget',
            '3',
            '--merge-budget',
            '2',
            '--scratch-soft-cap-gb',
            '123',
            stdout=output_buffer,
        )

        self.assertIn('policy=throughput', output_buffer.getvalue())
        manifest_path = scratch_root / f'listenbrainz/{infer_source_version_from_path(archive_path)}/full-ingestion-manifest.json'
        payload = json.loads(manifest_path.read_text(encoding='utf-8'))
        self.assertEqual(payload['runtime_control']['policy_mode'], FULL_INGESTION_POLICY_THROUGHPUT)
        self.assertEqual(payload['runtime_control']['partition_worker_budget'], 4)
        self.assertEqual(payload['runtime_control']['load_worker_budget'], 3)
        self.assertEqual(payload['runtime_control']['merge_worker_budget'], 2)


class FullIngestionExecutionTests(FullIngestionMixin, TransactionTestCase):
    def _create_track(self, *, spotify_id: str) -> Track:
        album = Album.objects.create(
            spotify_id=f'album-{spotify_id}',
            name=f'Album {spotify_id}',
            album_type='ALBUM',
            total_tracks=1,
            release_date='2024-01-01',
        )
        return Track.objects.create(
            spotify_id=spotify_id,
            name=f'Track {spotify_id}',
            album=album,
            track_number=1,
            disc_number=1,
            duration_ms=180000,
            explicit=False,
        )

    @override_settings(MLCORE_FULL_INGESTION_TARGET_CHUNK_ROWS=2)
    def test_copy_stage_loads_lean_event_and_session_rows(self):
        self._create_track(spotify_id='spotify-may')
        archive_path = self._build_archive()
        plan = build_full_ingestion_plan(
            'listenbrainz',
            archive_path,
            scratch_root=self.temp_dir / 'scratch',
            partition_count=4,
        )

        initialize_full_ingestion_plan(plan)
        extracted = execute_full_ingestion_partition_stage(plan)
        loaded = execute_full_ingestion_copy_stage(extracted)

        self.assertEqual(loaded.stage, 'copy')
        self.assertEqual(loaded.status, 'running')
        self.assertEqual(loaded.counters['rows_parsed'], 3)
        self.assertEqual(loaded.counters['rows_with_spotify_candidate'], 3)
        self.assertEqual(loaded.counters['rows_staged'], 3)
        self.assertEqual(loaded.counters['session_rows_loaded'], 3)
        self.assertGreaterEqual(loaded.counters['chunks_loaded'], 2)
        self.assertEqual(loaded.counters['partitions_loaded'], 4)
        self.assertTrue(all(partition.state == 'loaded' for partition in loaded.partitions))

        with connection.cursor() as cursor:
            cursor.execute(
                f'SELECT count(*) FROM {LISTENBRAINZ_EVENT_LOAD_TABLE} WHERE run_id = %s',
                [loaded.run_id],
            )
            event_load_rows = cursor.fetchone()[0]
            cursor.execute(
                f'SELECT count(*) FROM {LISTENBRAINZ_SESSION_LOAD_TABLE} WHERE run_id = %s',
                [loaded.run_id],
            )
            session_load_rows = cursor.fetchone()[0]
        self.assertEqual(event_load_rows, 3)
        self.assertEqual(session_load_rows, 3)

        populated_partition = next(
            partition for partition in loaded.partitions if partition.actual_artifact_count > 0
        )
        copy_manifest = full_ingestion_copy_manifest_path(loaded, partition_key=populated_partition.partition_key)
        self.assertTrue(copy_manifest.exists())
        copy_payload = json.loads(copy_manifest.read_text(encoding='utf-8'))
        self.assertIn('rows_loaded', copy_payload)
        self.assertIn('session_rows_loaded', copy_payload)

    def test_load_tables_have_partition_lookup_indexes(self):
        ensure_listenbrainz_load_tables()

        if connection.vendor == 'postgresql':
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT indexname
                    FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND tablename IN (%s, %s)
                    """,
                    [LISTENBRAINZ_EVENT_LOAD_TABLE, LISTENBRAINZ_SESSION_LOAD_TABLE],
                )
                index_names = {row[0] for row in cursor.fetchall()}
        else:
            index_names = set()
            with connection.cursor() as cursor:
                cursor.execute(f"PRAGMA index_list('{LISTENBRAINZ_EVENT_LOAD_TABLE}')")
                index_names.update(row[1] for row in cursor.fetchall())
                cursor.execute(f"PRAGMA index_list('{LISTENBRAINZ_SESSION_LOAD_TABLE}')")
                index_names.update(row[1] for row in cursor.fetchall())

        self.assertIn(f'{LISTENBRAINZ_EVENT_LOAD_TABLE}_run_partition_idx', index_names)
        self.assertIn(f'{LISTENBRAINZ_SESSION_LOAD_TABLE}_run_partition_idx', index_names)

    def test_merge_stage_populates_final_tables_and_cleans_load_tables(self):
        self._create_track(spotify_id='spotify-may')
        archive_path = self._build_archive()
        plan = build_full_ingestion_plan(
            'listenbrainz',
            archive_path,
            scratch_root=self.temp_dir / 'scratch',
            partition_count=4,
        )

        initialize_full_ingestion_plan(plan)
        extracted = execute_full_ingestion_partition_stage(plan)
        loaded = execute_full_ingestion_copy_stage(extracted)
        merged = execute_full_ingestion_merge_stage(loaded)

        self.assertEqual(merged.stage, 'complete')
        self.assertEqual(merged.status, 'succeeded')
        self.assertEqual(merged.counters['rows_merged'], 3)
        self.assertEqual(merged.counters['rows_deduplicated'], 0)
        self.assertEqual(merged.counters['rows_resolved'], 3)
        self.assertEqual(merged.counters['rows_resolved_by_spotify'], 3)
        self.assertEqual(merged.counters['rows_unresolved'], 0)
        self.assertEqual(merged.counters['partitions_merged'], 4)
        self.assertTrue(merged.source_ingestion_run_id)

        self.assertEqual(ListenBrainzEventLedger.objects.count(), 3)
        self.assertEqual(ListenBrainzSessionTrack.objects.count(), 3)
        self.assertEqual(ListenBrainzEventLedger.objects.filter(canonical_item__isnull=False).count(), 3)
        self.assertEqual(ListenBrainzEventLedger.objects.filter(track__isnull=False).count(), 1)

        source_run = SourceIngestionRun.objects.get(pk=merged.source_ingestion_run_id)
        self.assertEqual(source_run.status, 'succeeded')
        self.assertEqual(source_run.source_row_count, 3)
        self.assertEqual(source_run.imported_row_count, 3)
        self.assertEqual(source_run.unresolved_row_count, 0)
        self.assertEqual(source_run.metadata['full_ingestion_run_id'], merged.run_id)

        with connection.cursor() as cursor:
            cursor.execute(
                f'SELECT count(*) FROM {LISTENBRAINZ_EVENT_LOAD_TABLE} WHERE run_id = %s',
                [merged.run_id],
            )
            event_load_rows = cursor.fetchone()[0]
            cursor.execute(
                f'SELECT count(*) FROM {LISTENBRAINZ_SESSION_LOAD_TABLE} WHERE run_id = %s',
                [merged.run_id],
            )
            session_load_rows = cursor.fetchone()[0]
        self.assertEqual(event_load_rows, 0)
        self.assertEqual(session_load_rows, 0)

        if connection.vendor == 'postgresql':
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT EXISTS (
                        SELECT 1
                        FROM information_schema.tables
                        WHERE table_schema = current_schema()
                          AND table_name IN (
                              'mlcore_listenbrainz_event_ledger_build',
                              'mlcore_listenbrainz_event_ledger_old',
                              'mlcore_listenbrainz_session_track_build',
                              'mlcore_listenbrainz_session_track_old'
                          )
                    )
                    """
                )
                shadow_tables_exist = cursor.fetchone()[0]
            self.assertFalse(shadow_tables_exist)

    def test_pipeline_executor_completes_end_to_end(self):
        self._create_track(spotify_id='spotify-may')
        archive_path = self._build_archive()
        plan = build_full_ingestion_plan(
            'listenbrainz',
            archive_path,
            scratch_root=self.temp_dir / 'scratch',
            partition_count=4,
        )

        initialize_full_ingestion_plan(plan)
        completed = execute_full_ingestion_pipeline(plan)

        self.assertEqual(completed.stage, 'complete')
        self.assertEqual(completed.status, 'succeeded')
        self.assertEqual(completed.counters['rows_parsed'], 3)
        self.assertEqual(completed.counters['rows_staged'], 3)
        self.assertEqual(completed.counters['rows_merged'], 3)
        self.assertEqual(completed.counters['session_rows_loaded'], 3)
        self.assertEqual(completed.counters['partitions_loaded'], 4)
        self.assertEqual(completed.counters['partitions_merged'], 4)

    def test_command_can_execute_pipeline(self):
        self._create_track(spotify_id='spotify-may')
        archive_path = self._build_archive()
        scratch_root = self.temp_dir / 'scratch'
        output_buffer = StringIO()

        call_command(
            'ingest_dataset_full',
            '--provider',
            'listenbrainz',
            '--archive-path',
            str(archive_path),
            '--scratch-root',
            str(scratch_root),
            '--partition-count',
            '4',
            '--execute-pipeline',
            stdout=output_buffer,
        )

        source_version = infer_source_version_from_path(archive_path)
        manifest_path = scratch_root / f'listenbrainz/{source_version}/full-ingestion-manifest.json'
        payload = json.loads(manifest_path.read_text(encoding='utf-8'))
        self.assertEqual(payload['stage'], 'complete')
        self.assertEqual(payload['status'], 'succeeded')
        self.assertEqual(payload['counters']['rows_parsed'], 3)
        self.assertEqual(payload['counters']['rows_staged'], 3)
        self.assertEqual(payload['counters']['partitions_merged'], 4)
        self.assertIn('completed provider=listenbrainz', output_buffer.getvalue())

    def test_lease_blocks_legacy_tasks_and_remote_sync(self):
        FullIngestionLease.objects.create(
            provider='listenbrainz',
            holder_run_id='lease-run',
            source_version='listenbrainz-dump',
            status='running',
            metadata={'stage': 'partition'},
        )

        full_result = import_listenbrainz_full_task.run(dump_path=None, source_version=None)
        incremental_result = replay_listenbrainz_incremental_task.run(dump_path=None, source_version=None)
        sync_result = sync_listenbrainz_remote_dumps(download_dir=self.temp_dir / 'downloads')

        self.assertEqual(full_result['status'], 'skipped')
        self.assertEqual(full_result['reason'], 'full_ingestion_active')
        self.assertEqual(incremental_result['status'], 'skipped')
        self.assertEqual(incremental_result['reason'], 'full_ingestion_active')
        self.assertEqual(sync_result.status, 'skipped')

    def test_metrics_writer_handles_completed_status(self):
        archive_path = self._build_archive()
        metrics_path = self.temp_dir / 'metrics/mlcore_full_ingestion.prom'
        plan = build_full_ingestion_plan(
            'listenbrainz',
            archive_path,
            scratch_root=self.temp_dir / 'scratch',
            metrics_path=metrics_path,
        )
        completed = plan.__class__(**{
            **plan.__dict__,
            'status': 'succeeded',
            'stage': 'complete',
        })
        write_full_ingestion_metrics(completed)
        metrics_text = metrics_path.read_text(encoding='utf-8')
        self.assertIn('mlcore_full_ingestion_active{provider="listenbrainz"', metrics_text)
        self.assertIn('stage="complete"', metrics_text)

    def test_metrics_writer_uses_wall_clock_elapsed_for_running_status(self):
        archive_path = self._build_archive()
        metrics_path = self.temp_dir / 'metrics/mlcore_full_ingestion.prom'
        created_at = datetime.now(tz=UTC) - timedelta(hours=2)
        updated_at = created_at + timedelta(minutes=30)
        plan = build_full_ingestion_plan(
            'listenbrainz',
            archive_path,
            scratch_root=self.temp_dir / 'scratch',
            metrics_path=metrics_path,
        )
        running = plan.__class__(**{
            **plan.__dict__,
            'status': 'running',
            'stage': 'copy',
            'created_at': created_at.isoformat(),
            'updated_at': updated_at.isoformat(),
        })
        write_full_ingestion_metrics(running)
        metrics_text = metrics_path.read_text(encoding='utf-8')
        elapsed_line = next(
            line for line in metrics_text.splitlines()
            if line.startswith('mlcore_full_ingestion_elapsed_seconds{')
        )
        elapsed_seconds = float(elapsed_line.rsplit(' ', 1)[-1])
        self.assertGreater(elapsed_seconds, 3600)
