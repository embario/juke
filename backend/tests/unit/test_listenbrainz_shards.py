import json
import tarfile
import tempfile
from io import BytesIO, StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from mlcore.services.dataset_orchestration import (
    aggregate_dataset_progress,
    get_dataset_orchestration_service,
)
from mlcore.services.listenbrainz_shards import (
    build_listenbrainz_shard_orchestration,
    configured_listenbrainz_shard_root,
    materialize_listenbrainz_shards,
)


class ListenBrainzShardMaterializationTests(SimpleTestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp())

    def _build_archive(self, archive_name: str = 'listenbrainz-listens-dump-2446-20260301-000003-full.tar') -> Path:
        archive_path = self.temp_dir / archive_name
        with tarfile.open(archive_path, 'w') as archive:
            self._add_member(
                archive,
                'listenbrainz-listens-dump-2446-20260301-000003-full/listens/2007/5.listens',
                b'{"listened_at": 1}\n',
            )
            self._add_member(
                archive,
                'listenbrainz-listens-dump-2446-20260301-000003-full/listens/2007/6.listens',
                b'{"listened_at": 2}\n',
            )
            self._add_member(
                archive,
                'listenbrainz-listens-dump-2446-20260301-000003-full/listens/notes.txt',
                b'ignore me\n',
            )
            self._add_member(
                archive,
                'listenbrainz-listens-dump-2446-20260301-000003-full/stats/summary.json',
                b'{}',
            )
        return archive_path

    def _add_member(self, archive: tarfile.TarFile, name: str, payload: bytes) -> None:
        info = tarfile.TarInfo(name=name)
        info.size = len(payload)
        archive.addfile(info, BytesIO(payload))

    def test_materialize_extracts_monthly_shards_and_manifest(self):
        archive_path = self._build_archive()
        shard_root = self.temp_dir / 'shards'

        result = materialize_listenbrainz_shards(
            archive_path,
            shard_root=shard_root,
            shard_parallelism=3,
            max_shards_per_run=1,
        )

        output_root = shard_root / 'listenbrainz-dump-2446-20260301-000003-full'
        self.assertEqual(Path(result.output_root), output_root)
        self.assertEqual(result.shard_count, 2)
        self.assertEqual(
            (output_root / 'listens/2007/5.listens').read_text(encoding='utf-8'),
            '{"listened_at": 1}\n',
        )
        self.assertEqual(
            (output_root / 'listens/2007/6.listens').read_text(encoding='utf-8'),
            '{"listened_at": 2}\n',
        )
        self.assertFalse((output_root / 'stats/summary.json').exists())

        manifest = json.loads((output_root / 'manifest.json').read_text(encoding='utf-8'))
        self.assertEqual(manifest['source_version'], 'listenbrainz-dump-2446-20260301-000003-full')
        self.assertEqual(manifest['shard_count'], 2)
        self.assertEqual(
            [shard['relative_path'] for shard in manifest['shards']],
            ['listens/2007/5.listens', 'listens/2007/6.listens'],
        )
        self.assertEqual([shard['month'] for shard in manifest['shards']], [5, 6])
        orchestration = json.loads((output_root / 'orchestration.json').read_text(encoding='utf-8'))
        self.assertEqual(orchestration['shard_parallelism'], 3)
        self.assertEqual(orchestration['max_shards_per_run'], 1)
        self.assertEqual(orchestration['scheduled_shard_count'], 1)

    def test_materialize_requires_force_to_replace_existing_output(self):
        archive_path = self._build_archive()
        shard_root = self.temp_dir / 'shards'

        materialize_listenbrainz_shards(archive_path, shard_root=shard_root)

        reused = materialize_listenbrainz_shards(
            archive_path,
            shard_root=shard_root,
            shard_parallelism=5,
            max_shards_per_run=1,
        )
        orchestration = json.loads(
            (Path(reused.output_root) / 'orchestration.json').read_text(encoding='utf-8')
        )
        self.assertEqual(orchestration['shard_parallelism'], 5)
        self.assertEqual(orchestration['max_shards_per_run'], 1)

        result = materialize_listenbrainz_shards(archive_path, shard_root=shard_root, force=True)
        self.assertEqual(result.shard_count, 2)

    def test_materialize_still_requires_force_for_incomplete_existing_output(self):
        archive_path = self._build_archive()
        shard_root = self.temp_dir / 'shards'
        output_root = shard_root / 'listenbrainz-dump-2446-20260301-000003-full'
        output_root.mkdir(parents=True)

        with self.assertRaisesMessage(ValueError, 'Shard output already exists'):
            materialize_listenbrainz_shards(archive_path, shard_root=shard_root)

    @override_settings(
        MLCORE_LISTENBRAINZ_DOWNLOAD_DIR='/tmp/listenbrainz-downloads',
    )
    def test_configured_shard_root_nests_under_download_dir(self):
        self.assertEqual(
            configured_listenbrainz_shard_root(),
            Path('/tmp/listenbrainz-downloads/shards'),
        )

    def test_generic_command_defaults_to_provider_archive_and_shard_root(self):
        archive_path = self._build_archive(
            archive_name='listenbrainz-listens-dump-2550-20260401-000003-full.tar'
        )
        output_buffer = StringIO()

        download_dir = self.temp_dir / 'downloads'
        with override_settings(
            MLCORE_LISTENBRAINZ_FULL_IMPORT_PATH=str(archive_path),
            MLCORE_LISTENBRAINZ_DOWNLOAD_DIR=str(download_dir),
        ):
            call_command('materialize_dataset_shards', '--provider', 'listenbrainz', stdout=output_buffer)

        output_root = download_dir / 'shards/listenbrainz-dump-2550-20260401-000003-full'
        self.assertTrue((output_root / 'manifest.json').exists())
        self.assertTrue((output_root / 'orchestration.json').exists())
        self.assertIn('provider=listenbrainz', output_buffer.getvalue())

    def test_factory_returns_listenbrainz_service(self):
        self.assertEqual(
            get_dataset_orchestration_service('listenbrainz').provider,
            'listenbrainz',
        )

    def test_orchestration_plan_and_aggregate_progress(self):
        archive_path = self._build_archive()
        shard_root = self.temp_dir / 'shards'
        materialized = materialize_listenbrainz_shards(archive_path, shard_root=shard_root)

        plan = build_listenbrainz_shard_orchestration(
            source_version=materialized.source_version,
            manifest_path=materialized.manifest_path,
            output_root=materialized.output_root,
            shard_parallelism=4,
            max_shards_per_run=1,
        )
        self.assertEqual(plan.shard_parallelism, 4)
        self.assertEqual(plan.scheduled_shard_count, 1)

        aggregate = aggregate_dataset_progress(
            plan,
            [
                {
                    'status': 'running',
                    'source_row_count': 100,
                    'imported_row_count': 80,
                    'duplicate_row_count': 20,
                }
            ],
        )
        self.assertEqual(aggregate['running_shards'], 1)
        self.assertEqual(aggregate['source_row_count'], 100)
        self.assertEqual(aggregate['imported_row_count'], 80)
