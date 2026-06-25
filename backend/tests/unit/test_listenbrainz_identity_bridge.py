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
    CanonicalItemAlias,
    CanonicalItemRedirect,
    ListenBrainzIdentityShard,
    ListenBrainzMSIDMBIDConflictResolution,
    ListenBrainzMSIDMBIDMapping,
    SourceIngestionRun,
)
from mlcore.services.canonical_items import identity_from_parts
from mlcore.services.listenbrainz_identity_bridge import (
    CONFLICT_RESOLVER_SOURCE_ID,
    expand_listenbrainz_identity_graph,
    import_listenbrainz_identity_bridge,
    materialize_listenbrainz_isrc_aliases,
    resolve_listenbrainz_identity_conflicts,
)


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

    def _listen(self, msid, mbid=None, isrc=None):
        payload = {
            'recording_msid': str(msid),
            'track_metadata': {'additional_info': {}},
        }
        if mbid is not None:
            payload['track_metadata']['mbid_mapping'] = {'recording_mbid': str(mbid)}
        if isrc is not None:
            payload['track_metadata']['additional_info']['isrc'] = isrc
        return json.dumps(payload)

    def _write_manifest(self):
        contents = {
            '2000/01.jsonl': '\n'.join([
                self._listen(self.msid_one, self.mbid_one, 'USAAA2400001'),
                self._listen(self.msid_one, self.mbid_one, 'USAAA2400001'),
                self._listen(self.msid_two, self.mbid_two, 'USAAA2400002'),
                self._listen(self.msid_conflict, self.mbid_one, 'USAAA2400003'),
                self._listen(uuid.uuid4()),
                '{not-json',
            ]) + '\n',
            '2000/02.jsonl': '\n'.join([
                self._listen(self.msid_one, self.mbid_one, 'USAAA2400001'),
                self._listen(self.msid_conflict, self.mbid_two, 'USAAA2400003'),
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
        self.assertEqual(first.isrc_observation_count, 6)
        self.assertEqual(first.unique_isrc_pair_count, 5)
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

    def test_materializes_isrcs_directly_into_alias_graph(self):
        bridge = import_listenbrainz_identity_bridge(self.manifest_path, output_root=self.output_root)
        expand_listenbrainz_identity_graph(self.source_version)
        result = materialize_listenbrainz_isrc_aliases(self.source_version)
        repeated = materialize_listenbrainz_isrc_aliases(self.source_version)

        self.assertEqual(bridge.isrc_observation_count, 6)
        self.assertEqual(result.isrc_observation_count, 6)
        self.assertEqual(result.unique_msid_isrc_pair_count, 3)
        self.assertEqual(result.distinct_isrc_count, 3)
        self.assertEqual(result.materialized_alias_count, 3)
        self.assertEqual(result.ambiguous_isrc_count, 0)
        self.assertEqual(result.existing_alias_conflict_count, 0)
        self.assertEqual(result.unresolved_pair_count, 0)
        self.assertEqual(repeated.materialized_alias_count, 0)
        self.assertEqual(CanonicalItemAlias.objects.filter(source='isrc').count(), 3)
        alias = CanonicalItemAlias.objects.get(source='isrc', source_id='USAAA2400001')
        self.assertEqual(alias.canonical_item.canonical_key, f'recording_mbid:{self.mbid_one}')
        self.assertEqual(alias.metadata['match_source'], 'listenbrainz')

    def test_excludes_isrc_that_resolves_to_multiple_canonical_items(self):
        shared_isrc = 'USAAA2400099'
        manifest = json.loads(self.manifest_path.read_text())
        shard_path = self.root / manifest['shards'][0]['relative_path']
        with shard_path.open('a') as handle:
            handle.write(self._listen(self.msid_one, self.mbid_one, shared_isrc) + '\n')
            handle.write(self._listen(self.msid_two, self.mbid_two, shared_isrc) + '\n')
        manifest['shards'][0]['size_bytes'] = shard_path.stat().st_size
        manifest['shards'][0]['sha256'] = hashlib.sha256(shard_path.read_bytes()).hexdigest()
        self.manifest_path.write_text(json.dumps(manifest))

        import_listenbrainz_identity_bridge(self.manifest_path, output_root=self.output_root)
        expand_listenbrainz_identity_graph(self.source_version)
        result = materialize_listenbrainz_isrc_aliases(self.source_version)

        self.assertEqual(result.ambiguous_isrc_count, 1)
        self.assertFalse(CanonicalItemAlias.objects.filter(source='isrc', source_id=shared_isrc).exists())

    def test_invalid_isrc_does_not_discard_valid_msid_mbid_evidence(self):
        manifest = json.loads(self.manifest_path.read_text())
        shard_path = self.root / manifest['shards'][0]['relative_path']
        with shard_path.open('a') as handle:
            handle.write(self._listen(self.msid_one, self.mbid_one, 'not-an-isrc') + '\n')
        manifest['shards'][0]['size_bytes'] = shard_path.stat().st_size
        manifest['shards'][0]['sha256'] = hashlib.sha256(shard_path.read_bytes()).hexdigest()
        self.manifest_path.write_text(json.dumps(manifest))

        result = import_listenbrainz_identity_bridge(self.manifest_path, output_root=self.output_root)

        self.assertEqual(result.source_row_count, 9)
        self.assertEqual(result.mapped_row_count, 7)
        self.assertEqual(result.isrc_observation_count, 6)
        self.assertEqual(result.malformed_row_count, 2)

    def test_pre_isrc_checkpoint_is_reextracted_once(self):
        first = import_listenbrainz_identity_bridge(self.manifest_path, output_root=self.output_root)
        ListenBrainzIdentityShard.objects.filter(source_version=self.source_version).update(
            extraction_schema_version=1,
            isrc_observation_count=0,
            unique_isrc_pair_count=0,
        )
        for path in self.output_root.rglob('*.msid-isrc.tsv'):
            path.unlink()

        replay = import_listenbrainz_identity_bridge(self.manifest_path, output_root=self.output_root)

        self.assertEqual(first.isrc_observation_count, 6)
        self.assertEqual(replay.isrc_observation_count, 6)
        self.assertTrue(
            all(
                version == 2
                for version in ListenBrainzIdentityShard.objects.filter(
                    source_version=self.source_version
                ).values_list('extraction_schema_version', flat=True)
            )
        )

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

    def test_expansion_creates_missing_msid_items_and_materializes_redirects(self):
        import_listenbrainz_identity_bridge(self.manifest_path, output_root=self.output_root)
        missing_msid = uuid.uuid4()
        ListenBrainzMSIDMBIDMapping.objects.create(
            recording_msid=missing_msid,
            recording_mbid=self.mbid_two,
            source_version=self.source_version,
            shard_observation_count=4,
            first_shard='manual',
            last_shard='manual',
            status='active',
        )

        dry_run = expand_listenbrainz_identity_graph(self.source_version, batch_size=2, dry_run=True)
        result = expand_listenbrainz_identity_graph(self.source_version, batch_size=2)

        self.assertEqual(dry_run.missing_msid_count, 1)
        self.assertEqual(dry_run.created_msid_count, 0)
        self.assertEqual(result.missing_msid_count, 1)
        self.assertEqual(result.created_msid_count, 1)
        self.assertEqual(result.redirect_count, 3)
        self.assertTrue(CanonicalItem.objects.filter(canonical_key=f'recording_msid:{missing_msid}').exists())
        self.assertTrue(
            CanonicalItemRedirect.objects.filter(
                from_canonical_item__canonical_key=f'recording_msid:{missing_msid}',
                to_canonical_item__canonical_key=f'recording_mbid:{self.mbid_two}',
                status='active',
            ).exists()
        )

    def test_conflict_resolution_promotes_only_dominant_conflicts(self):
        import_listenbrainz_identity_bridge(self.manifest_path, output_root=self.output_root)
        dominant_msid = uuid.uuid4()
        loser_mbid = uuid.uuid4()
        self._create_item('recording_msid', dominant_msid)
        self._create_item('recording_mbid', loser_mbid)
        ListenBrainzMSIDMBIDMapping.objects.bulk_create([
            ListenBrainzMSIDMBIDMapping(
                recording_msid=dominant_msid,
                recording_mbid=self.mbid_one,
                source_version=self.source_version,
                shard_observation_count=20,
                first_shard='manual',
                last_shard='manual',
                status='conflict',
            ),
            ListenBrainzMSIDMBIDMapping(
                recording_msid=dominant_msid,
                recording_mbid=loser_mbid,
                source_version=self.source_version,
                shard_observation_count=1,
                first_shard='manual',
                last_shard='manual',
                status='conflict',
            ),
        ])

        dry_run = resolve_listenbrainz_identity_conflicts(
            self.source_version,
            min_winner_share=0.95,
            min_winner_shards=2,
            dry_run=True,
        )
        result = resolve_listenbrainz_identity_conflicts(
            self.source_version,
            min_winner_share=0.95,
            min_winner_shards=2,
        )

        self.assertEqual(dry_run.eligible_conflict_msid_count, 2)
        self.assertEqual(dry_run.resolved_msid_count, 1)
        self.assertEqual(result.resolved_msid_count, 1)
        self.assertEqual(result.redirect_count, 1)
        self.assertEqual(result.redirect_conflict_count, 0)
        resolution = ListenBrainzMSIDMBIDConflictResolution.objects.get(recording_msid=dominant_msid)
        self.assertEqual(resolution.chosen_recording_mbid, self.mbid_one)
        self.assertAlmostEqual(resolution.winner_share, 20 / 21)
        self.assertTrue(
            CanonicalItemRedirect.objects.filter(
                from_canonical_item__canonical_key=f'recording_msid:{dominant_msid}',
                to_canonical_item__canonical_key=f'recording_mbid:{self.mbid_one}',
                source=CONFLICT_RESOLVER_SOURCE_ID,
                status='active',
            ).exists()
        )
        self.assertFalse(
            CanonicalItemRedirect.objects.filter(
                from_canonical_item__canonical_key=f'recording_msid:{self.msid_conflict}',
                source=CONFLICT_RESOLVER_SOURCE_ID,
                status='active',
            ).exists()
        )

    def test_cold_evidence_and_unlogged_stage_placement(self):
        self.assertEqual(ListenBrainzMSIDMBIDMapping._meta.db_tablespace, 'juke_mlcore_cold')
        self.assertEqual(ListenBrainzIdentityShard._meta.db_tablespace, 'juke_mlcore_cold')
        self.assertEqual(ListenBrainzMSIDMBIDConflictResolution._meta.db_tablespace, 'juke_mlcore_cold')
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
