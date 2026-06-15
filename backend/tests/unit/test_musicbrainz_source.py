import hashlib
import io
import json
import tarfile
import tempfile
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.test import TestCase, override_settings

from mlcore.models import SourceIngestionRun
from mlcore.services.musicbrainz_source import (
    CORE_ARTIFACT_NAME,
    REQUIRED_CORE_MEMBERS,
    discover_musicbrainz_release,
    stage_musicbrainz_dump,
)


class _FakeResponse(io.BytesIO):
    def __init__(self, payload=b'', *, headers=None):
        super().__init__(payload)
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.close()
        return False


@override_settings(MLCORE_MUSICBRAINZ_REMOTE_TIMEOUT_SECONDS=1)
class MusicBrainzSourceTests(TestCase):
    source_version = '20260613-002047'
    root_url = 'https://data.example/musicbrainz/fullexport/'

    def setUp(self):
        self.download_dir = Path(tempfile.mkdtemp())
        self.archive_payload = self._build_archive_payload(REQUIRED_CORE_MEMBERS)
        self.archive_sha256 = hashlib.sha256(self.archive_payload).hexdigest()

    def _build_archive_payload(self, members):
        output = io.BytesIO()
        with tarfile.open(fileobj=output, mode='w:bz2') as archive:
            for member_name in members:
                payload = f'{member_name}\n'.encode()
                member = tarfile.TarInfo(member_name)
                member.size = len(payload)
                archive.addfile(member, io.BytesIO(payload))
        return output.getvalue()

    def _urlopen(self, *, artifact_payload=None, checksum=None):
        artifact_payload = self.archive_payload if artifact_payload is None else artifact_payload
        checksum = checksum or hashlib.sha256(artifact_payload).hexdigest()
        release_url = f'{self.root_url}{self.source_version}/'
        payloads = {
            ('GET', f'{self.root_url}LATEST'): _FakeResponse(self.source_version.encode()),
            ('GET', f'{release_url}SHA256SUMS'): _FakeResponse(
                f'{checksum} *{CORE_ARTIFACT_NAME}\n'.encode()
            ),
            ('HEAD', f'{release_url}{CORE_ARTIFACT_NAME}'): _FakeResponse(
                headers={'Content-Length': str(len(artifact_payload))}
            ),
            ('GET', f'{release_url}{CORE_ARTIFACT_NAME}'): _FakeResponse(artifact_payload),
        }

        def open_request(request, timeout=None):
            key = (request.get_method(), request.full_url)
            response = payloads.get(key)
            if response is None:
                raise AssertionError(f'unexpected request: {key}')
            return _FakeResponse(response.getvalue(), headers=response.headers)

        return mock.patch('mlcore.services.musicbrainz_source.urlopen', side_effect=open_request)

    def test_discovers_latest_core_dump_and_capacity_plan(self):
        with self._urlopen(), mock.patch(
            'mlcore.services.musicbrainz_source._available_bytes', return_value=500 * 1024**3
        ):
            plan = discover_musicbrainz_release(
                root_url=self.root_url,
                download_dir=self.download_dir,
                minimum_free_bytes=100 * 1024**3,
            )

        self.assertEqual(plan.source_version, self.source_version)
        self.assertEqual(plan.artifact.name, CORE_ARTIFACT_NAME)
        self.assertEqual(plan.artifact.sha256, self.archive_sha256)
        self.assertEqual(plan.artifact.compressed_bytes, len(self.archive_payload))
        self.assertEqual(plan.estimated_expanded_bytes, 80 * 1024**3)
        self.assertEqual(plan.minimum_free_bytes, 100 * 1024**3)
        self.assertEqual(plan.available_bytes, 500 * 1024**3)
        self.assertTrue(plan.release_dir.endswith(f'releases/{self.source_version}'))

    def test_stages_verified_archive_manifest_and_database_run(self):
        progress = []
        with self._urlopen(), mock.patch(
            'mlcore.services.musicbrainz_source._available_bytes', return_value=500 * 1024**3
        ):
            result = stage_musicbrainz_dump(
                root_url=self.root_url,
                download_dir=self.download_dir,
                minimum_free_bytes=1,
                progress_callback=progress.append,
            )

        self.assertEqual(result.status, 'succeeded')
        self.assertTrue(result.downloaded)
        self.assertTrue(Path(result.artifact_path).exists())
        self.assertFalse(Path(f'{result.artifact_path}.part').exists())
        manifest = json.loads(Path(result.manifest_path).read_text())
        self.assertEqual(manifest['source_version'], self.source_version)
        self.assertEqual(manifest['required_members'], list(REQUIRED_CORE_MEMBERS))
        self.assertEqual(manifest['artifacts'][0]['sha256'], self.archive_sha256)
        self.assertEqual(manifest['estimated_expanded_bytes'], 80 * 1024**3)
        self.assertTrue(Path(manifest['staging_dir']).is_dir())
        run = SourceIngestionRun.objects.get(id=result.run_id)
        self.assertEqual(run.status, 'succeeded')
        self.assertEqual(run.metadata['phase'], 'dump_stage')
        self.assertEqual(run.fingerprint, hashlib.sha256(
            json.dumps({
                'source': 'musicbrainz',
                'source_version': self.source_version,
                'manifest_version': 1,
                'required_members': list(REQUIRED_CORE_MEMBERS),
                'artifacts': [{
                    'name': CORE_ARTIFACT_NAME,
                    'sha256': self.archive_sha256,
                    'actual_bytes': len(self.archive_payload),
                }],
            }, sort_keys=True).encode()
        ).hexdigest())
        self.assertEqual(progress[-1]['downloaded_bytes'], len(self.archive_payload))

    def test_rerun_skips_download_and_reuses_successful_run(self):
        with self._urlopen(), mock.patch(
            'mlcore.services.musicbrainz_source._available_bytes', return_value=500 * 1024**3
        ):
            first = stage_musicbrainz_dump(
                root_url=self.root_url,
                download_dir=self.download_dir,
                minimum_free_bytes=1,
            )
        with self._urlopen() as mock_urlopen, mock.patch(
            'mlcore.services.musicbrainz_source._available_bytes', return_value=500 * 1024**3
        ):
            second = stage_musicbrainz_dump(
                root_url=self.root_url,
                download_dir=self.download_dir,
                minimum_free_bytes=1,
            )

        self.assertEqual(second.status, 'skipped')
        self.assertFalse(second.downloaded)
        self.assertEqual(second.run_id, first.run_id)
        artifact_gets = [
            call for call in mock_urlopen.call_args_list
            if call.args[0].get_method() == 'GET' and call.args[0].full_url.endswith(CORE_ARTIFACT_NAME)
        ]
        self.assertEqual(artifact_gets, [])
        self.assertEqual(SourceIngestionRun.objects.filter(source='musicbrainz').count(), 1)

    def test_verified_manual_archive_is_adopted_into_provenance(self):
        artifact_path = self.download_dir / 'releases' / self.source_version / 'raw' / CORE_ARTIFACT_NAME
        artifact_path.parent.mkdir(parents=True)
        artifact_path.write_bytes(self.archive_payload)

        with self._urlopen(), mock.patch(
            'mlcore.services.musicbrainz_source._available_bytes', return_value=500 * 1024**3
        ):
            result = stage_musicbrainz_dump(
                root_url=self.root_url,
                download_dir=self.download_dir,
                minimum_free_bytes=1,
            )

        self.assertEqual(result.status, 'skipped')
        self.assertIsNotNone(result.run_id)
        run = SourceIngestionRun.objects.get(id=result.run_id)
        self.assertTrue(run.metadata['adopted_existing_artifact'])
        self.assertEqual(run.status, 'succeeded')

    def test_refuses_download_when_cold_storage_is_below_reserve(self):
        with self._urlopen(), mock.patch(
            'mlcore.services.musicbrainz_source._available_bytes', return_value=10
        ):
            with self.assertRaisesRegex(RuntimeError, 'Insufficient MusicBrainz cold-storage capacity'):
                stage_musicbrainz_dump(
                    root_url=self.root_url,
                    download_dir=self.download_dir,
                    minimum_free_bytes=100,
                )

        self.assertFalse((self.download_dir / 'releases' / self.source_version / 'raw' / CORE_ARTIFACT_NAME).exists())
        self.assertEqual(SourceIngestionRun.objects.count(), 0)

    def test_checksum_failure_removes_partial_and_records_failed_run(self):
        expected_checksum = '0' * 64
        with self._urlopen(checksum=expected_checksum), mock.patch(
            'mlcore.services.musicbrainz_source._available_bytes', return_value=500 * 1024**3
        ):
            with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
                stage_musicbrainz_dump(
                    root_url=self.root_url,
                    download_dir=self.download_dir,
                    minimum_free_bytes=1,
                )

        artifact_path = self.download_dir / 'releases' / self.source_version / 'raw' / CORE_ARTIFACT_NAME
        self.assertFalse(artifact_path.exists())
        self.assertFalse(artifact_path.with_name(f'{CORE_ARTIFACT_NAME}.part').exists())
        run = SourceIngestionRun.objects.get()
        self.assertEqual(run.status, 'failed')
        self.assertIn('checksum mismatch', run.last_error)

    def test_missing_required_member_rejects_archive(self):
        incomplete = self._build_archive_payload(REQUIRED_CORE_MEMBERS[:-1])
        with self._urlopen(artifact_payload=incomplete), mock.patch(
            'mlcore.services.musicbrainz_source._available_bytes', return_value=500 * 1024**3
        ):
            with self.assertRaisesRegex(ValueError, 'missing required members'):
                stage_musicbrainz_dump(
                    root_url=self.root_url,
                    download_dir=self.download_dir,
                    minimum_free_bytes=1,
                )

        run = SourceIngestionRun.objects.get()
        self.assertEqual(run.status, 'failed')
        self.assertIn('mbdump/link_type', run.last_error)
        artifact_path = self.download_dir / 'releases' / self.source_version / 'raw' / CORE_ARTIFACT_NAME
        self.assertFalse(artifact_path.exists())

    @mock.patch('mlcore.management.commands.stage_musicbrainz_dump.discover_musicbrainz_release')
    def test_plan_command_emits_machine_readable_release_plan(self, mock_discover):
        with self._urlopen(), mock.patch(
            'mlcore.services.musicbrainz_source._available_bytes', return_value=500 * 1024**3
        ):
            mock_discover.return_value = discover_musicbrainz_release(
                root_url=self.root_url,
                download_dir=self.download_dir,
                minimum_free_bytes=100,
            )
        stdout = io.StringIO()

        call_command('stage_musicbrainz_dump', '--plan', '--json', stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload['source_version'], self.source_version)
        self.assertEqual(payload['artifact']['name'], CORE_ARTIFACT_NAME)
