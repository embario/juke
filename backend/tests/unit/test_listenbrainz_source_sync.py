import tempfile
import uuid
from datetime import timedelta
from io import BytesIO
from pathlib import Path
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone

from mlcore.ingestion.listenbrainz import ImportResult
from mlcore.models import SourceIngestionRun
from mlcore.services.listenbrainz_source import sync_listenbrainz_remote_dumps


class _FakeResponse(BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False


@override_settings(
    MLCORE_LISTENBRAINZ_REMOTE_TIMEOUT_SECONDS=1,
)
class ListenBrainzRemoteSyncTests(TestCase):
    def setUp(self):
        self.download_dir = Path(tempfile.mkdtemp())
        self.root_url = 'https://ftp.example/listenbrainz/'
        self.full_release_dir = (
            'https://ftp.example/listenbrainz/fullexport/'
            'listenbrainz-dump-2446-20260301-000003-full/'
        )
        self.full_archive_url = (
            f'{self.full_release_dir}'
            'listenbrainz-listens-dump-2446-20260301-000003-full.tar.zst'
        )
        self.incremental_2447_dir = (
            'https://ftp.example/listenbrainz/incremental/'
            'listenbrainz-dump-2447-20260302-000003-incremental/'
        )
        self.incremental_2447_archive_url = (
            f'{self.incremental_2447_dir}'
            'listenbrainz-listens-dump-2447-20260302-000003-incremental.tar.zst'
        )
        self.incremental_2448_dir = (
            'https://ftp.example/listenbrainz/incremental/'
            'listenbrainz-dump-2448-20260303-000003-incremental/'
        )
        self.incremental_2448_archive_url = (
            f'{self.incremental_2448_dir}'
            'listenbrainz-listens-dump-2448-20260303-000003-incremental.tar.zst'
        )

    def _urlopen_side_effect(self, payloads: dict[str, bytes]):
        def _open(request, timeout=None):
            url = request.full_url
            if url not in payloads:
                raise AssertionError(f'unexpected url: {url}')
            return _FakeResponse(payloads[url])

        return _open

    def _import_result(self) -> ImportResult:
        return ImportResult(
            run_id=uuid.uuid4(),
            status='succeeded',
            source_row_count=1,
            imported_row_count=1,
            duplicate_row_count=0,
            canonicalized_row_count=1,
            unresolved_row_count=0,
            malformed_row_count=0,
            checksum='checksum',
        )

    @mock.patch('mlcore.services.listenbrainz_source.import_listenbrainz_dump')
    @mock.patch('mlcore.services.listenbrainz_source.urlopen')
    def test_sync_downloads_latest_full_and_missing_incrementals(self, mock_urlopen, mock_import):
        mock_urlopen.side_effect = self._urlopen_side_effect({
            'https://ftp.example/listenbrainz/fullexport/': b'''
                <a href="../">../</a>
                <a href="listenbrainz-dump-2446-20260301-000003-full/">full</a>
            ''',
            self.full_release_dir: b'''
                <a href="listenbrainz-listens-dump-2446-20260301-000003-full.tar.zst">archive</a>
            ''',
            self.full_archive_url: b'FULL',
            'https://ftp.example/listenbrainz/incremental/': b'''
                <a href="listenbrainz-dump-2445-20260228-000003-incremental/">old-inc</a>
                <a href="listenbrainz-dump-2447-20260302-000003-incremental/">inc-1</a>
                <a href="listenbrainz-dump-2448-20260303-000003-incremental/">inc-2</a>
            ''',
            self.incremental_2447_dir: b'''
                <a href="listenbrainz-listens-dump-2447-20260302-000003-incremental.tar.zst">archive</a>
            ''',
            self.incremental_2447_archive_url: b'INC1',
            self.incremental_2448_dir: b'''
                <a href="listenbrainz-listens-dump-2448-20260303-000003-incremental.tar.zst">archive</a>
            ''',
            self.incremental_2448_archive_url: b'INC2',
        })
        mock_import.side_effect = lambda dump_path, **kwargs: self._import_result()

        result = sync_listenbrainz_remote_dumps(
            root_url=self.root_url,
            download_dir=self.download_dir,
            max_incrementals_per_run=10,
        )

        self.assertEqual(result.status, 'succeeded')
        self.assertEqual(result.full_source_version, 'listenbrainz-dump-2446-20260301-000003-full')
        self.assertEqual(
            result.incremental_source_versions,
            [
                'listenbrainz-dump-2447-20260302-000003-incremental',
                'listenbrainz-dump-2448-20260303-000003-incremental',
            ],
        )
        self.assertEqual(mock_import.call_count, 3)
        imported_versions = [call.kwargs['source_version'] for call in mock_import.call_args_list]
        self.assertEqual(
            imported_versions,
            [
                'listenbrainz-dump-2446-20260301-000003-full',
                'listenbrainz-dump-2447-20260302-000003-incremental',
                'listenbrainz-dump-2448-20260303-000003-incremental',
            ],
        )
        for path in result.downloaded_paths:
            self.assertTrue(Path(path).exists())

    @mock.patch('mlcore.services.listenbrainz_source.import_listenbrainz_dump')
    @mock.patch('mlcore.services.listenbrainz_source.urlopen')
    def test_sync_logs_start_discovery_and_completion(self, mock_urlopen, mock_import):
        mock_urlopen.side_effect = self._urlopen_side_effect({
            'https://ftp.example/listenbrainz/fullexport/': b'''
                <a href="listenbrainz-dump-2446-20260301-000003-full/">full</a>
            ''',
            self.full_release_dir: b'''
                <a href="listenbrainz-listens-dump-2446-20260301-000003-full.tar.zst">archive</a>
            ''',
            self.full_archive_url: b'FULL',
            'https://ftp.example/listenbrainz/incremental/': b'',
        })
        mock_import.side_effect = lambda dump_path, **kwargs: self._import_result()

        with self.assertLogs('mlcore.services.listenbrainz_source', level='INFO') as captured:
            result = sync_listenbrainz_remote_dumps(
                root_url=self.root_url,
                download_dir=self.download_dir,
                max_incrementals_per_run=5,
            )

        self.assertEqual(result.status, 'succeeded')
        log_output = '\n'.join(captured.output)
        self.assertIn('listenbrainz remote sync starting', log_output)
        self.assertIn('discovered full releases=1', log_output)
        self.assertIn('discovered incrementals=0 candidates_after_baseline=0', log_output)
        self.assertIn('listenbrainz remote sync completed status=succeeded', log_output)

    @mock.patch('mlcore.services.listenbrainz_source.import_listenbrainz_dump')
    @mock.patch('mlcore.services.listenbrainz_source.urlopen')
    def test_sync_only_imports_incrementals_missing_after_existing_full(self, mock_urlopen, mock_import):
        SourceIngestionRun.objects.create(
            source='listenbrainz',
            import_mode='full',
            source_version='listenbrainz-listens-dump-2446-20260301-000003-full.tar.zst',
            raw_path='/tmp/full.tar.zst',
            checksum='checksum',
            status='succeeded',
            completed_at='2026-03-23T00:00:00Z',
        )
        SourceIngestionRun.objects.create(
            source='listenbrainz',
            import_mode='incremental',
            source_version='listenbrainz-dump-2447-20260302-000003-incremental',
            raw_path='/tmp/inc1.tar.zst',
            checksum='checksum',
            status='succeeded',
            completed_at='2026-03-23T00:00:00Z',
        )
        mock_urlopen.side_effect = self._urlopen_side_effect({
            'https://ftp.example/listenbrainz/incremental/': b'''
                <a href="listenbrainz-dump-2447-20260302-000003-incremental/">inc-1</a>
                <a href="listenbrainz-dump-2448-20260303-000003-incremental/">inc-2</a>
            ''',
            self.incremental_2448_dir: b'''
                <a href="listenbrainz-listens-dump-2448-20260303-000003-incremental.tar.zst">archive</a>
            ''',
            self.incremental_2448_archive_url: b'INC2',
        })
        mock_import.side_effect = lambda dump_path, **kwargs: self._import_result()

        result = sync_listenbrainz_remote_dumps(
            root_url=self.root_url,
            download_dir=self.download_dir,
            max_incrementals_per_run=10,
        )

        self.assertEqual(result.full_source_version, None)
        self.assertEqual(
            result.incremental_source_versions,
            ['listenbrainz-dump-2448-20260303-000003-incremental'],
        )
        self.assertEqual(mock_import.call_count, 1)
        self.assertEqual(
            mock_import.call_args.kwargs['source_version'],
            'listenbrainz-dump-2448-20260303-000003-incremental',
        )

    @mock.patch('mlcore.services.listenbrainz_source.import_listenbrainz_dump')
    @mock.patch('mlcore.services.listenbrainz_source.urlopen')
    def test_sync_imports_local_full_baseline_before_checking_incrementals(self, mock_urlopen, mock_import):
        local_full = self.download_dir / 'listenbrainz-listens-dump-2446-20260301-000003-full.tar.zst'
        local_full.write_bytes(b'FULL')
        mock_urlopen.side_effect = self._urlopen_side_effect({
            'https://ftp.example/listenbrainz/incremental/': b'''
                <a href="listenbrainz-dump-2447-20260302-000003-incremental/">inc-1</a>
            ''',
            self.incremental_2447_dir: b'''
                <a href="listenbrainz-listens-dump-2447-20260302-000003-incremental.tar.zst">archive</a>
            ''',
            self.incremental_2447_archive_url: b'INC1',
        })
        mock_import.side_effect = lambda dump_path, **kwargs: self._import_result()

        result = sync_listenbrainz_remote_dumps(
            root_url=self.root_url,
            download_dir=self.download_dir,
            max_incrementals_per_run=10,
        )

        self.assertEqual(result.status, 'succeeded')
        self.assertEqual(result.full_source_version, 'listenbrainz-dump-2446-20260301-000003-full')
        self.assertEqual(
            result.incremental_source_versions,
            ['listenbrainz-dump-2447-20260302-000003-incremental'],
        )
        self.assertEqual(
            [call.kwargs['source_version'] for call in mock_import.call_args_list],
            [
                'listenbrainz-dump-2446-20260301-000003-full',
                'listenbrainz-dump-2447-20260302-000003-incremental',
            ],
        )

    @mock.patch('mlcore.services.listenbrainz_source.import_listenbrainz_dump')
    @mock.patch('mlcore.services.listenbrainz_source.urlopen')
    def test_sync_noops_when_local_full_baseline_is_already_in_flight(self, mock_urlopen, mock_import):
        local_full = self.download_dir / 'listenbrainz-listens-dump-2446-20260301-000003-full.tar.zst'
        local_full.write_bytes(b'FULL')
        SourceIngestionRun.objects.create(
            source='listenbrainz',
            import_mode='full',
            source_version='listenbrainz-listens-dump-2446-20260301-000003-full.tar.zst',
            raw_path=str(local_full),
            checksum='checksum',
            status='running',
        )

        result = sync_listenbrainz_remote_dumps(
            root_url=self.root_url,
            download_dir=self.download_dir,
            max_incrementals_per_run=10,
        )

        self.assertEqual(result.status, 'noop')
        self.assertEqual(result.downloaded_paths, [])
        self.assertEqual(result.incremental_source_versions, [])
        self.assertEqual(
            result.skipped_source_versions,
            ['listenbrainz-dump-2446-20260301-000003-full'],
        )
        mock_import.assert_not_called()
        mock_urlopen.assert_not_called()

    @mock.patch('mlcore.services.listenbrainz_source.import_listenbrainz_dump')
    @mock.patch('mlcore.services.listenbrainz_source.urlopen')
    def test_sync_logs_in_flight_incremental_skips(self, mock_urlopen, mock_import):
        SourceIngestionRun.objects.create(
            source='listenbrainz',
            import_mode='full',
            source_version='listenbrainz-dump-2446-20260301-000003-full',
            raw_path='/tmp/full.tar.zst',
            checksum='checksum',
            status='succeeded',
            completed_at='2026-03-23T00:00:00Z',
        )
        SourceIngestionRun.objects.create(
            source='listenbrainz',
            import_mode='incremental',
            source_version='listenbrainz-dump-2447-20260302-000003-incremental',
            raw_path='/tmp/inc1.tar.zst',
            checksum='checksum',
            status='running',
        )
        mock_urlopen.side_effect = self._urlopen_side_effect({
            'https://ftp.example/listenbrainz/fullexport/': b'''
                <a href="listenbrainz-dump-2446-20260301-000003-full/">full</a>
            ''',
            'https://ftp.example/listenbrainz/incremental/': b'''
                <a href="listenbrainz-dump-2447-20260302-000003-incremental/">inc-1</a>
            ''',
        })
        mock_import.side_effect = lambda dump_path, **kwargs: self._import_result()

        with self.assertLogs('mlcore.services.listenbrainz_source', level='INFO') as captured:
            result = sync_listenbrainz_remote_dumps(
                root_url=self.root_url,
                download_dir=self.download_dir,
                max_incrementals_per_run=10,
            )

        self.assertEqual(result.status, 'noop')
        self.assertIn(
            'skipping incremental=listenbrainz-dump-2447-20260302-000003-incremental because it is already in flight',
            '\n'.join(captured.output),
        )

    @mock.patch('mlcore.services.listenbrainz_source.import_listenbrainz_dump')
    @mock.patch('mlcore.services.listenbrainz_source.urlopen')
    def test_sync_reuses_legacy_root_artifact_without_redownloading(self, mock_urlopen, mock_import):
        legacy_artifact = self.download_dir / 'listenbrainz-listens-dump-2446-20260301-000003-full.tar.zst'
        legacy_artifact.write_bytes(b'FULL')
        mock_urlopen.side_effect = self._urlopen_side_effect({
            'https://ftp.example/listenbrainz/fullexport/': b'''
                <a href="listenbrainz-dump-2446-20260301-000003-full/">full</a>
            ''',
            'https://ftp.example/listenbrainz/fullexport/listenbrainz-dump-2446-20260301-000003-full/': b'''
                <a href="listenbrainz-listens-dump-2446-20260301-000003-full.tar.zst">archive</a>
            ''',
            'https://ftp.example/listenbrainz/incremental/': b'',
        })
        mock_import.side_effect = lambda dump_path, **kwargs: self._import_result()

        result = sync_listenbrainz_remote_dumps(
            root_url=self.root_url,
            download_dir=self.download_dir,
            max_incrementals_per_run=1,
        )

        self.assertEqual(result.status, 'succeeded')
        self.assertEqual(result.downloaded_paths, [])
        self.assertEqual(Path(mock_import.call_args.args[0]), legacy_artifact)

    @override_settings(MLCORE_LISTENBRAINZ_STALE_INFLIGHT_TIMEOUT_SECONDS=60)
    @mock.patch('mlcore.services.listenbrainz_source.import_listenbrainz_dump')
    @mock.patch('mlcore.services.listenbrainz_source.urlopen')
    def test_sync_expires_stale_inflight_run_before_reimporting_local_full(self, mock_urlopen, mock_import):
        local_full = self.download_dir / 'listenbrainz-listens-dump-2446-20260301-000003-full.tar.zst'
        local_full.write_bytes(b'FULL')
        stale_started_at = timezone.now() - timedelta(minutes=10)
        run = SourceIngestionRun.objects.create(
            source='listenbrainz',
            import_mode='full',
            source_version='listenbrainz-dump-2446-20260301-000003-full',
            raw_path=str(local_full),
            checksum='checksum',
            status='running',
            metadata={'last_progress_at': stale_started_at.isoformat()},
        )
        SourceIngestionRun.objects.filter(pk=run.pk).update(started_at=stale_started_at)
        mock_urlopen.side_effect = self._urlopen_side_effect({
            'https://ftp.example/listenbrainz/incremental/': b'',
        })
        mock_import.side_effect = lambda dump_path, **kwargs: self._import_result()

        result = sync_listenbrainz_remote_dumps(
            root_url=self.root_url,
            download_dir=self.download_dir,
            max_incrementals_per_run=1,
        )

        self.assertEqual(result.status, 'succeeded')
        self.assertEqual(result.full_source_version, 'listenbrainz-dump-2446-20260301-000003-full')
        run.refresh_from_db()
        self.assertEqual(run.status, 'failed')
        self.assertIn('Stale in-flight ListenBrainz import marked failed', run.last_error)
        self.assertIn('stale_marked_at', run.metadata)
        self.assertEqual(mock_import.call_count, 1)

    @mock.patch('mlcore.services.listenbrainz_source.urlopen')
    @mock.patch('mlcore.services.listenbrainz_source.LicensePolicy')
    def test_sync_skips_when_policy_blocks_source(self, mock_policy_cls, mock_urlopen):
        mock_policy_cls.return_value.classify_source.return_value = 'blocked'

        result = sync_listenbrainz_remote_dumps(
            root_url=self.root_url,
            download_dir=self.download_dir,
        )

        self.assertEqual(result.status, 'skipped')
        self.assertEqual(result.policy_classification, 'blocked')
        mock_urlopen.assert_not_called()
