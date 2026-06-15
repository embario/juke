import hashlib
import io
import json
import tempfile
import uuid
from pathlib import Path

from django.core.management import call_command
from django.db import connection
from django.test import TestCase

from mlcore.models import (
    CanonicalItem,
    CanonicalItemRedirect,
    ListenBrainzIdentityShard,
    ListenBrainzMSIDMBIDMapping,
    SourceIngestionRun,
)
from mlcore.services.canonical_items import identity_from_parts
from mlcore.services.listenbrainz_identity_bridge import import_listenbrainz_identity_bridge


class ListenBrainzIdentityBridgeTests(TestCase):
    source_version = 'listenbrainz-test-v1'

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.output_root = self.root / 'identity-evidence'
        self.msid_one = uuid.uuid4()
        self.msid_two = uuid.uuid4()
        self.msid_conflict = uuid.uuid4()
        self.mbid_one = uuid.uuid4()
        self.mbid_two = uuid.uuid4()
        self._create_item('recording_msid', self.msid_one)
        self._create_item('recording_msid', self.msid_two)
        self._create_item('recording_msid', self.msid_conflict)
        self._create_item('recording_mbid', self.mbid_one)
        self._create_item('recording_mbid', self.mbid_two)
        self.manifest_path = self._write_manifest()

    def tearDown(self):
        self.temp_dir.cleanup()

    def _create_item(self, item_type, value):
        identity = identity_from_parts(item_type=item_type, key_value=value)
        return CanonicalItem.objects.create(
            id=identity.item_id,
            item_type=identity.item_type,
            canonical_key=identity.canonical_key,
        )

    def _listen(self, msid, mbid=None):
        payload = {
            'recording_msid': str(msid),
            'track_metadata': {'additional_info': {}},
        }
        if mbid is not None:
            payload['track_metadata']['mbid_mapping'] = {'recording_mbid': str(mbid)}
        return json.dumps(payload)

    def _write_manifest(self):
        contents = {
            '2000/01.jsonl': '\n'.join([
                self._listen(self.msid_one, self.mbid_one),
                self._listen(self.msid_one, self.mbid_one),
                self._listen(self.msid_two, self.mbid_two),
                self._listen(self.msid_conflict, self.mbid_one),
                self._listen(uuid.uuid4()),
                '{not-json',
            ]) + '\n',
            '2000/02.jsonl': '\n'.join([
                self._listen(self.msid_one, self.mbid_one),
                self._listen(self.msid_conflict, self.mbid_two),
            ]) + '\n',
        }
        shards = []
        for relative_path, content in contents.items():
            path = self.root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
            shards.append({
                'relative_path': relative_path,
                'size_bytes': path.stat().st_size,
                'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            })
        manifest = {
            'source': 'listenbrainz',
            'source_version': self.source_version,
            'shards': shards,
        }
        path = self.root / 'manifest.json'
        path.write_text(json.dumps(manifest))
        return path

    def test_imports_exact_pairs_resumes_idempotently_and_materializes_safe_redirects(self):
        first = import_listenbrainz_identity_bridge(self.manifest_path, output_root=self.output_root)
        second = import_listenbrainz_identity_bridge(self.manifest_path, output_root=self.output_root)

        self.assertEqual(first.source_row_count, 8)
        self.assertEqual(first.mapped_row_count, 6)
        self.assertEqual(first.unique_pair_count, 5)
        self.assertEqual(first.malformed_row_count, 1)
        self.assertEqual(first.active_mapping_count, 2)
        self.assertEqual(first.conflict_msid_count, 1)
        self.assertEqual(first.redirect_count, 2)
        self.assertEqual(first.redirect_conflict_count, 0)
        self.assertEqual(second.active_mapping_count, 2)
        self.assertEqual(ListenBrainzMSIDMBIDMapping.objects.count(), 4)
        self.assertEqual(CanonicalItemRedirect.objects.filter(status='active').count(), 2)
        self.assertEqual(ListenBrainzIdentityShard.objects.filter(status='succeeded').count(), 2)

        repeated = ListenBrainzMSIDMBIDMapping.objects.get(
            recording_msid=self.msid_one,
            recording_mbid=self.mbid_one,
        )
        self.assertEqual(repeated.shard_observation_count, 2)
        self.assertEqual(
            ListenBrainzMSIDMBIDMapping.objects.filter(
                recording_msid=self.msid_conflict,
                status='conflict',
            ).count(),
            2,
        )
        self.assertEqual(SourceIngestionRun.objects.filter(status='succeeded').count(), 2)

    def test_full_run_retires_redirects_created_by_partial_validation_run(self):
        partial = import_listenbrainz_identity_bridge(self.manifest_path, output_root=self.output_root, max_shards=1)
        self.assertEqual(partial.redirect_count, 3)
        self.assertEqual(CanonicalItemRedirect.objects.filter(status='active').count(), 3)

        final = import_listenbrainz_identity_bridge(self.manifest_path, output_root=self.output_root)

        self.assertEqual(final.redirect_count, 2)
        self.assertEqual(CanonicalItemRedirect.objects.filter(status='active').count(), 2)
        self.assertEqual(
            CanonicalItemRedirect.objects.filter(
                from_canonical_item__canonical_key=f'recording_msid:{self.msid_conflict}',
                status='retired',
            ).count(),
            1,
        )

    def test_cold_evidence_and_unlogged_stage_placement(self):
        self.assertEqual(ListenBrainzMSIDMBIDMapping._meta.db_tablespace, 'juke_mlcore_cold')
        self.assertEqual(ListenBrainzIdentityShard._meta.db_tablespace, 'juke_mlcore_cold')
        with connection.cursor() as cursor:
            cursor.execute('''
                SELECT c.relname, t.spcname, c.relpersistence
                FROM pg_class c
                JOIN pg_tablespace t ON t.oid = c.reltablespace
                WHERE c.relname IN (
                    'mlcore_listenbrainz_identity_pair_stage',
                    'mlcore_listenbrainz_msid_mbid_mapping',
                    'mlcore_listenbrainz_identity_shard',
                    'mlcore_canonical_item_redirect'
                )
            ''')
            placement = {name: (tablespace, persistence) for name, tablespace, persistence in cursor.fetchall()}

        self.assertEqual(placement['mlcore_listenbrainz_identity_pair_stage'], ('juke_mlcore_cold', 'u'))
        self.assertEqual(placement['mlcore_listenbrainz_msid_mbid_mapping'][0], 'juke_mlcore_cold')
        self.assertEqual(placement['mlcore_listenbrainz_identity_shard'][0], 'juke_mlcore_cold')
        self.assertEqual(placement['mlcore_canonical_item_redirect'][0], 'juke_mlcore_hot')

    def test_command_emits_json(self):
        stdout = io.StringIO()

        call_command(
            'import_listenbrainz_identity_bridge',
            '--manifest',
            str(self.manifest_path),
            '--output-root',
            str(self.output_root),
            '--json',
            stdout=stdout,
        )

        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload['source_version'], self.source_version)
        self.assertEqual(payload['redirect_count'], 2)
