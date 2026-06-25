import hashlib
import io
import json
import tarfile
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.db import connection
from django.test import TestCase

from mlcore.models import (
    MusicBrainzRecordingISRC,
    MusicBrainzRecordingURL,
    SourceIngestionRun,
)
from mlcore.services.musicbrainz_bridge import classify_provider, import_musicbrainz_bridge


class MusicBrainzBridgeTests(TestCase):
    source_version = '20260613-002047'
    recording_mbid = '12345678-1234-4234-9234-123456789abc'

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.archive_path = self.root / 'mbdump.tar.bz2'
        self.manifest_path = self.root / 'manifest.json'
        self._write_archive()
        checksum = hashlib.sha256(self.archive_path.read_bytes()).hexdigest()
        self.manifest_path.write_text(json.dumps({
            'source': 'musicbrainz',
            'source_version': self.source_version,
            'artifacts': [{
                'name': 'mbdump.tar.bz2',
                'path': str(self.archive_path),
                'sha256': checksum,
            }],
        }))

    def _write_archive(self):
        members = {
            'mbdump/recording': (
                f'1\t{self.recording_mbid}\tTest Recording\t1\t180000\t\\N\t0\t2026-01-01\tf\n'
                '2\t87654321-4321-4321-8321-cba987654321\tOther\t1\t200000\t\\N\t0\t2026-01-01\tf\n'
            ),
            'mbdump/isrc': (
                '10\t1\tUSABC2600001\t0\t2026-01-01\n'
                '11\t1\tUSABC2600001\t0\t2026-01-01\n'
                '12\t1\tbad-isrc\t0\t2026-01-01\n'
                '13\t2\tGBXYZ2500002\t0\t2026-01-01\n'
            ),
            'mbdump/url': (
                '20\t11111111-1111-4111-8111-111111111111\thttps://open.spotify.com/track/spotify123\t0\t2026-01-01\n'
                '21\t22222222-2222-4222-8222-222222222222\thttps://example.com/recording\t0\t2026-01-01\n'
            ),
            'mbdump/l_recording_url': (
                '30\t40\t1\t20\t0\t2026-01-01\t0\t\\N\t\\N\n'
                '31\t40\t1\t21\t0\t2026-01-01\t0\t\\N\t\\N\n'
            ),
            'mbdump/link': '40\t50\t\\N\t\\N\t\\N\t\\N\t\\N\t\\N\t0\t2026-01-01\tf\n',
            'mbdump/link_type': (
                '50\t\\N\t0\t33333333-3333-4333-8333-333333333333\trecording\turl\tstreaming\t'
                'Streaming page\thas streaming page\tis streaming page for\tstreaming pages\t0\t2026-01-01\n'
            ),
        }
        with tarfile.open(self.archive_path, mode='w:bz2') as archive:
            for name, value in members.items():
                payload = value.encode()
                member = tarfile.TarInfo(name)
                member.size = len(payload)
                archive.addfile(member, io.BytesIO(payload))

    def test_imports_idempotent_isrc_and_url_evidence_with_provenance(self):
        first = import_musicbrainz_bridge(self.manifest_path)
        second = import_musicbrainz_bridge(self.manifest_path)

        self.assertEqual(first.recording_rows, 2)
        self.assertEqual(first.isrc_rows, 4)
        self.assertEqual(first.valid_isrc_rows, 3)
        self.assertEqual(first.malformed_isrc_rows, 1)
        self.assertEqual(first.duplicate_isrc_rows, 1)
        self.assertEqual(first.unique_recordings_with_isrc, 2)
        self.assertEqual(first.inserted_isrc_rows, 2)
        self.assertEqual(first.url_relationship_rows, 2)
        self.assertEqual(first.extracted_url_rows, 2)
        self.assertEqual(first.inserted_url_rows, 2)
        self.assertEqual(second.inserted_isrc_rows, 0)
        self.assertEqual(second.inserted_url_rows, 0)
        self.assertEqual(MusicBrainzRecordingISRC.objects.count(), 2)
        self.assertEqual(MusicBrainzRecordingURL.objects.count(), 2)

        spotify = MusicBrainzRecordingURL.objects.get(provider='spotify')
        self.assertEqual(str(spotify.recording_mbid), self.recording_mbid)
        self.assertEqual(spotify.link_type_name, 'streaming')
        self.assertEqual(spotify.url_fingerprint, hashlib.md5(spotify.url.encode()).hexdigest())

        run = SourceIngestionRun.objects.get(pk=first.run_id)
        self.assertEqual(run.source, 'musicbrainz-identity-bridge')
        self.assertEqual(run.status, 'succeeded')
        self.assertEqual(run.source_version, self.source_version)
        self.assertEqual(run.malformed_row_count, 1)
        self.assertEqual(run.metadata['tablespace'], 'juke_mlcore_cold')

    def test_checksum_failure_records_no_run(self):
        manifest = json.loads(self.manifest_path.read_text())
        manifest['artifacts'][0]['sha256'] = '0' * 64
        self.manifest_path.write_text(json.dumps(manifest))

        with self.assertRaisesRegex(ValueError, 'checksum mismatch'):
            import_musicbrainz_bridge(self.manifest_path)

        self.assertFalse(SourceIngestionRun.objects.exists())

    def test_bridge_and_staging_tables_are_cold(self):
        self.assertEqual(MusicBrainzRecordingISRC._meta.db_tablespace, 'juke_mlcore_cold')
        self.assertEqual(MusicBrainzRecordingURL._meta.db_tablespace, 'juke_mlcore_cold')
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT c.relname, t.spcname, c.relpersistence
                FROM pg_class c
                JOIN pg_tablespace t ON t.oid = c.reltablespace
                WHERE c.relname IN (
                    'mlcore_mb_recording_stage',
                    'mlcore_mb_isrc_stage',
                    'mlcore_musicbrainz_recording_isrc',
                    'mlcore_musicbrainz_recording_url'
                )
            ''')
            placement = {name: (tablespace, persistence) for name, tablespace, persistence in cursor.fetchall()}

        self.assertEqual(placement['mlcore_musicbrainz_recording_isrc'][0], 'juke_mlcore_cold')
        self.assertEqual(placement['mlcore_musicbrainz_recording_url'][0], 'juke_mlcore_cold')
        self.assertEqual(placement['mlcore_mb_recording_stage'], ('juke_mlcore_cold', 'u'))
        self.assertEqual(placement['mlcore_mb_isrc_stage'], ('juke_mlcore_cold', 'u'))

    def test_command_emits_json(self):
        stdout = io.StringIO()

        call_command('import_musicbrainz_bridge', '--manifest', str(self.manifest_path), '--json', stdout=stdout)

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload['source_version'], self.source_version)
        self.assertEqual(payload['inserted_isrc_rows'], 2)

    def test_provider_classification(self):
        self.assertEqual(classify_provider('https://open.spotify.com/track/abc'), 'spotify')
        self.assertEqual(classify_provider('https://music.apple.com/us/song/example/1'), 'apple_music')
        self.assertEqual(classify_provider('https://example.com/track'), 'other')
