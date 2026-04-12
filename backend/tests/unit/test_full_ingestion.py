import json
import tarfile
import tempfile
from io import BytesIO, StringIO
from pathlib import Path
from unittest.mock import patch

from django.core.management import call_command
from django.db import connection
from django.test import SimpleTestCase, TransactionTestCase, override_settings

from catalog.models import Album, Track
from mlcore.models import ListenBrainzEventLedger, ListenBrainzSessionTrack, SourceIngestionRun
from mlcore.services.full_ingestion import (
    LISTENBRAINZ_EVENT_STAGE_TABLE,
    ListenBrainzFullIngestionProvider,
    build_full_ingestion_partition_estimates,
    build_full_ingestion_plan,
    execute_full_ingestion_copy_stage,
    execute_full_ingestion_merge_stage,
    execute_full_ingestion_pipeline,
    execute_full_ingestion_partition_stage,
    ensure_listenbrainz_staging_tables,
    full_ingestion_copy_manifest_path,
    full_ingestion_merge_manifest_path,
    full_ingestion_partition_manifest_path,
    initialize_full_ingestion_plan,
    load_full_ingestion_plan,
    partition_index_for_path,
    write_full_ingestion_metrics,
)
from mlcore.ingestion.listenbrainz import infer_source_version_from_path
from mlcore.services.listenbrainz_shards import materialize_listenbrainz_shards


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


class FullIngestionPlanningTests(FullIngestionMixin, SimpleTestCase):

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
        self.assertIn('mlcore_full_ingestion_artifacts_partitioned{provider="listenbrainz"', metrics_text)

    def test_partition_stage_extracts_provider_artifacts_and_writes_partition_manifests(self):
        archive_path = self._build_archive()
        metrics_path = self.temp_dir / 'metrics/mlcore_full_ingestion.prom'
        plan = build_full_ingestion_plan(
            'listenbrainz',
            archive_path,
            scratch_root=self.temp_dir / 'scratch',
            partition_count=4,
            metrics_path=metrics_path,
        )

        initialize_full_ingestion_plan(plan)
        partitioned = execute_full_ingestion_partition_stage(plan)

        self.assertEqual(partitioned.stage, 'partition')
        self.assertEqual(partitioned.status, 'running')
        self.assertEqual(partitioned.counters['artifacts_discovered'], 2)
        self.assertEqual(partitioned.counters['artifacts_partitioned'], 2)
        expected_partition_bytes = len(self.may_payload) + len(self.june_payload)
        self.assertEqual(partitioned.counters['input_bytes_partitioned'], expected_partition_bytes)
        self.assertEqual(partitioned.counters['partitions_completed'], 4)
        self.assertTrue(all(partition.state == 'partitioned' for partition in partitioned.partitions))

        partition_key_for_may = f"p{partition_index_for_path('listens/2007/5.listens', partition_count=4):03d}"
        partition_key_for_june = f"p{partition_index_for_path('listens/2007/6.listens', partition_count=4):03d}"
        artifact_paths = sorted(
            path.relative_to(Path(partitioned.partition_root)).as_posix()
            for path in Path(partitioned.partition_root).glob('p*/input/listens/*/*.listens')
        )
        self.assertEqual(
            artifact_paths,
            sorted(
                [
                    f'{partition_key_for_june}/input/listens/2007/6.listens',
                    f'{partition_key_for_may}/input/listens/2007/5.listens',
                ]
            ),
        )

        partition_manifest = full_ingestion_partition_manifest_path(partitioned, partition_key=partition_key_for_june)
        self.assertTrue(partition_manifest.exists())
        manifest_payload = json.loads(partition_manifest.read_text(encoding='utf-8'))
        self.assertEqual(manifest_payload['artifact_count'], 1)
        self.assertEqual(manifest_payload['artifacts'][0]['relative_path'], 'listens/2007/6.listens')

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
        manifest_path = (
            scratch_root
            / 'listenbrainz/listenbrainz-dump-2550-20260401-000003-full/full-ingestion-manifest.json'
        )
        self.assertTrue(manifest_path.exists())
        payload = json.loads(manifest_path.read_text(encoding='utf-8'))
        self.assertEqual(payload['partition_count'], 6)
        self.assertEqual(payload['worker_config']['partition_workers'], 5)

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

    def test_command_can_execute_partition_stage(self):
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
            '--execute-partition-stage',
            stdout=output_buffer,
        )

        source_version = infer_source_version_from_path(archive_path)
        manifest_path = (
            scratch_root
            / f'listenbrainz/{source_version}/full-ingestion-manifest.json'
        )
        payload = json.loads(manifest_path.read_text(encoding='utf-8'))
        self.assertEqual(payload['stage'], 'partition')
        self.assertEqual(payload['status'], 'running')
        self.assertEqual(payload['counters']['artifacts_partitioned'], 2)

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
        self.assertIn('states=partitioned:4', output)

    def test_status_command_can_emit_json(self):
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
            '--json',
            stdout=output_buffer,
        )
        payload = json.loads(output_buffer.getvalue())
        self.assertEqual(payload['provider'], 'listenbrainz')
        self.assertEqual(payload['status'], 'planned')
        self.assertEqual(payload['partition_count'], 128)


class FullIngestionCopyTests(FullIngestionMixin, TransactionTestCase):
    def _create_track(self, *, spotify_id: str, mbid=None) -> Track:
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
            mbid=mbid,
        )

    def test_copy_stage_loads_partition_rows_into_staging_table(self):
        archive_path = self._build_archive()
        plan = build_full_ingestion_plan(
            'listenbrainz',
            archive_path,
            scratch_root=self.temp_dir / 'scratch',
            partition_count=4,
        )

        initialize_full_ingestion_plan(plan)
        partitioned = execute_full_ingestion_partition_stage(plan)
        loaded = execute_full_ingestion_copy_stage(partitioned)

        self.assertEqual(loaded.stage, 'copy')
        self.assertEqual(loaded.status, 'running')
        self.assertEqual(loaded.counters['rows_parsed'], 3)
        self.assertEqual(loaded.counters['rows_staged'], 3)
        self.assertEqual(loaded.counters['rows_malformed'], 0)
        self.assertEqual(loaded.counters['partitions_loaded'], 4)
        self.assertTrue(all(partition.state == 'loaded' for partition in loaded.partitions))

        partition_key_for_june = f"p{partition_index_for_path('listens/2007/6.listens', partition_count=4):03d}"
        copy_manifest = full_ingestion_copy_manifest_path(loaded, partition_key=partition_key_for_june)
        self.assertTrue(copy_manifest.exists())
        copy_payload = json.loads(copy_manifest.read_text(encoding='utf-8'))
        self.assertEqual(copy_payload['rows_staged'], 2)

        with connection.cursor() as cursor:
            cursor.execute(
                f'''
                SELECT count(*), min(origin), max(origin)
                FROM {LISTENBRAINZ_EVENT_STAGE_TABLE}
                WHERE run_id = %s
                ''',
                [loaded.run_id],
            )
            row_count, min_origin, max_origin = cursor.fetchone()
        self.assertEqual(row_count, 3)
        self.assertEqual(min_origin, 'listens/2007/5.listens')
        self.assertEqual(max_origin, 'listens/2007/6.listens')

    def test_staging_table_has_partition_lookup_index(self):
        ensure_listenbrainz_staging_tables()

        if connection.vendor == 'postgresql':
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT indexname
                    FROM pg_indexes
                    WHERE schemaname = current_schema()
                      AND tablename = %s
                    """,
                    [LISTENBRAINZ_EVENT_STAGE_TABLE],
                )
                index_names = {row[0] for row in cursor.fetchall()}
        else:
            with connection.cursor() as cursor:
                cursor.execute(f"PRAGMA index_list('{LISTENBRAINZ_EVENT_STAGE_TABLE}')")
                index_names = {row[1] for row in cursor.fetchall()}

        self.assertIn(
            f'{LISTENBRAINZ_EVENT_STAGE_TABLE}_run_partition_idx',
            index_names,
        )

    def test_copy_stage_records_only_failed_partitions(self):
        archive_path = self._build_archive()
        plan = build_full_ingestion_plan(
            'listenbrainz',
            archive_path,
            scratch_root=self.temp_dir / 'scratch',
            partition_count=4,
        )

        initialize_full_ingestion_plan(plan)
        partitioned = execute_full_ingestion_partition_stage(plan)
        original_load = ListenBrainzFullIngestionProvider.load_partition_to_staging
        failed_partition_key: str | None = None

        def flaky_load(provider, current_plan, partition):
            nonlocal failed_partition_key
            if failed_partition_key is None:
                failed_partition_key = partition.partition_key
                raise RuntimeError('boom')
            return original_load(provider, current_plan, partition)

        with patch.object(ListenBrainzFullIngestionProvider, 'load_partition_to_staging', autospec=True, side_effect=flaky_load):
            with self.assertRaises(RuntimeError):
                execute_full_ingestion_copy_stage(partitioned)

        failed = load_full_ingestion_plan(partitioned.manifest_path)
        self.assertEqual(failed.status, 'failed')
        self.assertEqual(failed.counters['partitions_failed'], 1)
        self.assertEqual(
            sum(1 for partition in failed.partitions if partition.state == 'failed'),
            1,
        )
        self.assertEqual(
            [partition.partition_key for partition in failed.partitions if partition.state == 'failed'],
            [failed_partition_key],
        )

    def test_command_can_execute_copy_stage(self):
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
            '--execute-copy-stage',
            stdout=output_buffer,
        )

        source_version = infer_source_version_from_path(archive_path)
        manifest_path = scratch_root / f'listenbrainz/{source_version}/full-ingestion-manifest.json'
        payload = json.loads(manifest_path.read_text(encoding='utf-8'))
        self.assertEqual(payload['stage'], 'copy')
        self.assertEqual(payload['status'], 'running')
        self.assertEqual(payload['counters']['rows_staged'], 3)
        self.assertIn('loaded provider=listenbrainz', output_buffer.getvalue())

    def test_merge_stage_populates_final_tables_and_completes_run(self):
        self._create_track(spotify_id='spotify-may')
        archive_path = self._build_archive()
        plan = build_full_ingestion_plan(
            'listenbrainz',
            archive_path,
            scratch_root=self.temp_dir / 'scratch',
            partition_count=4,
        )

        initialize_full_ingestion_plan(plan)
        partitioned = execute_full_ingestion_partition_stage(plan)
        loaded = execute_full_ingestion_copy_stage(partitioned)
        merged = execute_full_ingestion_merge_stage(loaded)

        self.assertEqual(merged.stage, 'complete')
        self.assertEqual(merged.status, 'succeeded')
        self.assertEqual(merged.counters['rows_merged'], 3)
        self.assertEqual(merged.counters['rows_deduplicated'], 0)
        self.assertEqual(merged.counters['rows_resolved'], 1)
        self.assertEqual(merged.counters['rows_unresolved'], 2)
        self.assertEqual(merged.counters['partitions_merged'], 4)
        self.assertTrue(all(partition.state == 'merged' for partition in merged.partitions))
        self.assertTrue(merged.source_ingestion_run_id)

        partition_key_for_may = f"p{partition_index_for_path('listens/2007/5.listens', partition_count=4):03d}"
        merge_manifest = full_ingestion_merge_manifest_path(merged, partition_key=partition_key_for_may)
        self.assertTrue(merge_manifest.exists())
        merge_payload = json.loads(merge_manifest.read_text(encoding='utf-8'))
        self.assertEqual(merge_payload['rows_resolved'], 1)

        self.assertEqual(ListenBrainzEventLedger.objects.count(), 3)
        self.assertEqual(ListenBrainzSessionTrack.objects.count(), 1)
        session_track = ListenBrainzSessionTrack.objects.get()
        self.assertEqual(session_track.play_count, 1)
        self.assertEqual(ListenBrainzEventLedger.objects.filter(track__isnull=False).count(), 1)

        source_run = SourceIngestionRun.objects.get(pk=merged.source_ingestion_run_id)
        self.assertEqual(source_run.status, 'succeeded')
        self.assertEqual(source_run.source_row_count, 3)
        self.assertEqual(source_run.imported_row_count, 3)
        self.assertEqual(source_run.unresolved_row_count, 2)
        self.assertEqual(source_run.metadata['full_ingestion_run_id'], merged.run_id)

        with connection.cursor() as cursor:
            cursor.execute(
                f'SELECT count(*) FROM {LISTENBRAINZ_EVENT_STAGE_TABLE} WHERE run_id = %s',
                [merged.run_id],
            )
            remaining_stage_rows = cursor.fetchone()[0]
        self.assertEqual(remaining_stage_rows, 0)

    def test_command_can_execute_merge_stage(self):
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
            '--execute-merge-stage',
            stdout=output_buffer,
        )

        source_version = infer_source_version_from_path(archive_path)
        manifest_path = scratch_root / f'listenbrainz/{source_version}/full-ingestion-manifest.json'
        payload = json.loads(manifest_path.read_text(encoding='utf-8'))
        self.assertEqual(payload['stage'], 'complete')
        self.assertEqual(payload['status'], 'succeeded')
        self.assertEqual(payload['counters']['rows_merged'], 3)
        self.assertEqual(payload['counters']['rows_resolved'], 1)
        self.assertIn('completed provider=listenbrainz', output_buffer.getvalue())

    def test_pipeline_executor_completes_with_shared_lanes(self):
        self._create_track(spotify_id='spotify-may')
        archive_path = self._build_archive()
        plan = build_full_ingestion_plan(
            'listenbrainz',
            archive_path,
            scratch_root=self.temp_dir / 'scratch',
            partition_count=4,
            load_workers=2,
            merge_workers=2,
        )

        initialize_full_ingestion_plan(plan)
        completed = execute_full_ingestion_pipeline(plan)

        self.assertEqual(completed.stage, 'complete')
        self.assertEqual(completed.status, 'succeeded')
        self.assertEqual(completed.counters['rows_merged'], 3)
        self.assertEqual(completed.counters['partitions_loaded'], 4)
        self.assertEqual(completed.counters['partitions_merged'], 4)
        self.assertTrue(all(partition.state == 'merged' for partition in completed.partitions))

    def test_pipeline_resume_does_not_double_count_loaded_partitions(self):
        self._create_track(spotify_id='spotify-may')
        archive_path = self._build_archive()
        plan = build_full_ingestion_plan(
            'listenbrainz',
            archive_path,
            scratch_root=self.temp_dir / 'scratch',
            partition_count=4,
            load_workers=2,
            merge_workers=2,
        )

        initialize_full_ingestion_plan(plan)
        partitioned = execute_full_ingestion_partition_stage(plan)
        loaded = execute_full_ingestion_copy_stage(partitioned)
        completed = execute_full_ingestion_pipeline(loaded)

        self.assertEqual(completed.counters['partitions_loaded'], 4)
        self.assertEqual(completed.counters['partitions_merged'], 4)

    def test_failed_merge_persists_canonicalized_count(self):
        self._create_track(spotify_id='spotify-may')
        archive_path = self._build_archive()
        plan = build_full_ingestion_plan(
            'listenbrainz',
            archive_path,
            scratch_root=self.temp_dir / 'scratch',
            partition_count=2,
        )

        initialize_full_ingestion_plan(plan)
        partitioned = execute_full_ingestion_partition_stage(plan)
        loaded = execute_full_ingestion_copy_stage(partitioned)
        original_merge = ListenBrainzFullIngestionProvider.merge_partition_to_final
        failed_once = False

        def flaky_merge(provider, current_plan, partition, *, source_ingestion_run):
            nonlocal failed_once
            if failed_once:
                raise RuntimeError('merge boom')
            failed_once = True
            return original_merge(
                provider,
                current_plan,
                partition,
                source_ingestion_run=source_ingestion_run,
            )

        with patch.object(ListenBrainzFullIngestionProvider, 'merge_partition_to_final', autospec=True, side_effect=flaky_merge):
            with self.assertRaises(RuntimeError):
                execute_full_ingestion_merge_stage(loaded)

        source_run = SourceIngestionRun.objects.order_by('-started_at', '-pk').first()
        self.assertIsNotNone(source_run)
        self.assertEqual(source_run.status, 'failed')
        self.assertGreater(source_run.imported_row_count, 0)
        self.assertEqual(source_run.imported_row_count, source_run.canonicalized_row_count)

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
        self.assertEqual(payload['counters']['partitions_loaded'], 4)
        self.assertEqual(payload['counters']['partitions_merged'], 4)
        self.assertIn('completed provider=listenbrainz', output_buffer.getvalue())

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
