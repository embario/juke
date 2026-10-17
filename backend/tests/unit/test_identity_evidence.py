import io
import json
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from unittest import mock

from django.core.management import call_command
from django.db import connection
from django.test import TestCase

from mlcore.models import IdentityEvidence, IdentityEvidenceLoadGroup, ListenBrainzIdentityShard
from mlcore.services import identity_evidence
from mlcore.services.canonical_items import ITEM_TYPE_RECORDING_MSID, canonical_item_uuid
from mlcore.services.identity_evidence import (
    APPLY_BATCH_SQL,
    RAW_STAGE_TABLE,
    STAGE_TABLE,
    load_listenbrainz_identity_evidence,
    shard_period,
)
from mlcore.services.listenbrainz_identity_bridge import extract_listenbrainz_identity_shard

SPOTIFY_A = '4uLU6hMCjMI75M1A2tKUQC'
SPOTIFY_B = '1DFixLWgh2zZWvxKbdw5Rk'
SOURCE_VERSION = 'listenbrainz-evidence-test-v1'


class IdentityEvidenceLoaderTests(TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.output_root = self.root / 'evidence'
        self.msid_a, self.msid_b, self.msid_c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        self.mbid = uuid.uuid4()
        self._write_shard('2000/01.jsonl', [
            (self.msid_a, SPOTIFY_A, 'USAAA2400001', self.mbid),
            (self.msid_a, SPOTIFY_A, 'USAAA2400001', self.mbid),
            (self.msid_b, SPOTIFY_A, None, None),
            (self.msid_c, SPOTIFY_B, 'USAAA2400002', None),
        ])
        self._write_shard('2000/02.jsonl', [
            (self.msid_a, SPOTIFY_A, 'USAAA2400001', self.mbid),
            (self.msid_a, SPOTIFY_B, None, None),
        ])
        self._write_shard('2000/03.jsonl', [
            (self.msid_c, SPOTIFY_B, 'USAAA2400002', None),
        ])

    def tearDown(self):
        self.temp_dir.cleanup()

    def _write_shard(self, shard_key, rows):
        source = self.root / 'src' / shard_key
        source.parent.mkdir(parents=True, exist_ok=True)
        lines = []
        for msid, spotify, isrc, mbid in rows:
            info = {'spotify_id': spotify}
            if isrc:
                info['isrc'] = isrc
            payload = {'recording_msid': str(msid), 'track_metadata': {'additional_info': info}}
            if mbid:
                payload['track_metadata']['mbid_mapping'] = {'recording_mbid': str(mbid)}
            lines.append(json.dumps(payload))
        source.write_text('\n'.join(lines) + '\n')
        extract_listenbrainz_identity_shard(
            source,
            source_version=SOURCE_VERSION,
            shard_key=shard_key,
            source_sha256='0' * 64,
            output_root=self.output_root,
        )
        ListenBrainzIdentityShard.objects.filter(
            source_version=SOURCE_VERSION, shard_key=shard_key,
        ).update(status='succeeded')

    def _rows(self, scheme):
        return {
            (row.subject_canonical_item_id, row.value): row
            for row in IdentityEvidence.objects.filter(scheme=scheme)
        }

    def _subject(self, msid):
        return canonical_item_uuid(item_type=ITEM_TYPE_RECORDING_MSID, key_value=str(msid))

    def _snapshot(self):
        return sorted(
            IdentityEvidence.objects.values_list(
                'scheme', 'value', 'subject_canonical_item_id', 'observation_count', 'shard_count', 'first_seen', 'last_seen',
            )
        )

    def test_aggregates_counts_shards_and_period_across_files(self):
        result = load_listenbrainz_identity_evidence(SOURCE_VERSION, schemes=['spotify_track'], group_size=2)

        rows = self._rows('spotify_track')
        a_a = rows[(self._subject(self.msid_a), SPOTIFY_A)]
        self.assertEqual((a_a.observation_count, a_a.shard_count), (3, 2))
        self.assertEqual(a_a.first_seen, datetime(2000, 1, 1, tzinfo=UTC))
        self.assertEqual(a_a.last_seen, datetime(2000, 2, 1, tzinfo=UTC))
        self.assertEqual(a_a.source, 'listenbrainz')
        self.assertEqual(a_a.source_version, SOURCE_VERSION)
        a_b = rows[(self._subject(self.msid_a), SPOTIFY_B)]
        self.assertEqual((a_b.observation_count, a_b.shard_count), (1, 1))
        c_b = rows[(self._subject(self.msid_c), SPOTIFY_B)]
        self.assertEqual((c_b.observation_count, c_b.shard_count), (2, 2))
        self.assertEqual(len(rows), 4)
        self.assertEqual(result.groups_loaded, 2)  # 3 shard files, group size 2
        self.assertEqual(result.raw_row_count, 6)
        self.assertEqual(result.evidence_row_count, 5)  # per-group aggregates, merged by the upsert
        self.assertEqual(IdentityEvidenceLoadGroup.objects.filter(status='succeeded').count(), 2)

    def test_subject_is_derived_without_canonical_item_rows(self):
        load_listenbrainz_identity_evidence(SOURCE_VERSION, schemes=['spotify_track'])
        self.assertTrue(IdentityEvidence.objects.filter(subject_canonical_item_id=self._subject(self.msid_b)).exists())

    def test_isrc_and_mbid_schemes(self):
        load_listenbrainz_identity_evidence(SOURCE_VERSION, schemes=['isrc', 'mbid'])

        isrc = self._rows('isrc')
        self.assertEqual(isrc[(self._subject(self.msid_a), 'USAAA2400001')].observation_count, 3)
        self.assertEqual(isrc[(self._subject(self.msid_c), 'USAAA2400002')].shard_count, 2)
        mbid = self._rows('mbid')
        row = mbid[(self._subject(self.msid_a), str(self.mbid))]
        self.assertEqual((row.observation_count, row.shard_count), (2, 2))  # one observation per shard

    def test_group_size_does_not_change_the_result(self):
        load_listenbrainz_identity_evidence(SOURCE_VERSION, group_size=1)
        small = self._snapshot()
        IdentityEvidence.objects.all().delete()
        IdentityEvidenceLoadGroup.objects.all().delete()
        load_listenbrainz_identity_evidence(SOURCE_VERSION, group_size=12, batch_size=2)
        self.assertEqual(self._snapshot(), small)

    def test_rerun_is_idempotent(self):
        load_listenbrainz_identity_evidence(SOURCE_VERSION)
        first = self._snapshot()
        again = load_listenbrainz_identity_evidence(SOURCE_VERSION)
        self.assertEqual(self._snapshot(), first)
        self.assertEqual(again.groups_loaded, 0)
        self.assertEqual(again.groups_skipped, 3)  # one group per scheme

    def test_interrupted_load_resumes_without_double_counting(self):
        load_listenbrainz_identity_evidence(SOURCE_VERSION, schemes=['spotify_track'], group_size=12)
        expected = self._snapshot()
        IdentityEvidence.objects.all().delete()
        IdentityEvidenceLoadGroup.objects.all().delete()

        real_apply = identity_evidence._apply_batch
        calls = []

        def flaky(group, *, lower, upper):
            calls.append((lower, upper))
            if len(calls) == 3:
                raise RuntimeError('simulated crash')
            return real_apply(group, lower=lower, upper=upper)

        with mock.patch.object(identity_evidence, '_apply_batch', flaky):
            with self.assertRaises(RuntimeError):
                load_listenbrainz_identity_evidence(SOURCE_VERSION, schemes=['spotify_track'], batch_size=1)
        group = IdentityEvidenceLoadGroup.objects.get()
        self.assertEqual((group.status, group.applied_through), ('failed', 2))
        self.assertEqual(IdentityEvidence.objects.count(), 2)

        resumed = load_listenbrainz_identity_evidence(SOURCE_VERSION, schemes=['spotify_track'], batch_size=1)
        self.assertEqual(self._snapshot(), expected)
        self.assertEqual(resumed.groups_loaded, 1)
        self.assertEqual(IdentityEvidenceLoadGroup.objects.get().status, 'succeeded')

    def test_lost_stage_table_is_rebuilt_and_resumes_from_the_cursor(self):
        load_listenbrainz_identity_evidence(SOURCE_VERSION, schemes=['spotify_track'])
        expected = self._snapshot()
        IdentityEvidence.objects.all().delete()
        IdentityEvidenceLoadGroup.objects.all().delete()

        real_apply = identity_evidence._apply_batch
        calls = []

        def flaky(group, *, lower, upper):
            calls.append(lower)
            if len(calls) == 2:
                raise RuntimeError('simulated crash')
            return real_apply(group, lower=lower, upper=upper)

        with mock.patch.object(identity_evidence, '_apply_batch', flaky):
            with self.assertRaises(RuntimeError):
                load_listenbrainz_identity_evidence(SOURCE_VERSION, schemes=['spotify_track'], batch_size=1)
        with connection.cursor() as cursor:  # what a Postgres crash does to UNLOGGED tables
            cursor.execute(f'TRUNCATE {STAGE_TABLE}')

        load_listenbrainz_identity_evidence(SOURCE_VERSION, schemes=['spotify_track'], batch_size=1)
        self.assertEqual(self._snapshot(), expected)

    def test_staging_goes_to_the_requested_tablespace_and_is_dropped_afterwards(self):
        def fail_after_staging(group, *, lower, upper):
            raise RuntimeError('stop after staging')

        with mock.patch.object(identity_evidence, '_apply_batch', fail_after_staging):
            with self.assertRaises(RuntimeError):
                load_listenbrainz_identity_evidence(
                    SOURCE_VERSION, schemes=['spotify_track'], staging_tablespace='juke_mlcore_cold',
                )
        with connection.cursor() as cursor:
            cursor.execute(
                '''
                SELECT COALESCE(ts.spcname, 'pg_default'), c.relpersistence
                FROM pg_class c LEFT JOIN pg_tablespace ts ON ts.oid = c.reltablespace
                WHERE c.relname = %s
                ''',
                [STAGE_TABLE],
            )
            self.assertEqual(cursor.fetchone(), ('juke_mlcore_cold', 'u'))
            cursor.execute('SELECT to_regclass(%s)', [RAW_STAGE_TABLE])
            self.assertIsNone(cursor.fetchone()[0], 'raw staging is dropped once aggregated')

        load_listenbrainz_identity_evidence(SOURCE_VERSION, schemes=['spotify_track'], staging_tablespace='juke_mlcore_cold')
        with connection.cursor() as cursor:
            cursor.execute('SELECT to_regclass(%s)', [STAGE_TABLE])
            self.assertIsNone(cursor.fetchone()[0], 'staging is dropped once the group succeeds')

    def test_rejects_bad_options(self):
        for kwargs in (
            {'staging_tablespace': 'nvme; DROP TABLE x'},
            {'group_size': 0},
            {'batch_size': 0},
            {'work_mem': '1GB; DROP'},
            {'schemes': ['nope']},
        ):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    load_listenbrainz_identity_evidence(SOURCE_VERSION, **kwargs)

    def test_relocated_output_root(self):
        moved = self.root / 'moved'
        # Shards were written with output_root as the root itself; mirror that layout under <root>/<version>.
        for path in self.output_root.rglob('*.zst'):
            target = moved / SOURCE_VERSION / path.relative_to(self.output_root)
            target.parent.mkdir(parents=True, exist_ok=True)
            path.rename(target)
        load_listenbrainz_identity_evidence(SOURCE_VERSION, schemes=['spotify_track'], output_root=moved)
        self.assertEqual(IdentityEvidence.objects.filter(scheme='spotify_track').count(), 4)

    def test_missing_file_fails_the_group_and_is_retried(self):
        for path in self.output_root.rglob('2000/02.jsonl.msid-spotify.tsv.zst'):
            path.unlink()
        with self.assertRaises(FileNotFoundError):
            load_listenbrainz_identity_evidence(SOURCE_VERSION, schemes=['spotify_track'])
        self.assertEqual(IdentityEvidenceLoadGroup.objects.get().status, 'failed')
        self.assertEqual(IdentityEvidence.objects.count(), 0)

    def test_shard_period(self):
        fallback = datetime(2026, 1, 1, tzinfo=UTC)
        self.assertEqual(shard_period('2007/05.jsonl', fallback), datetime(2007, 5, 1, tzinfo=UTC))
        self.assertEqual(shard_period('listens/2007/5.listens', fallback), datetime(2007, 5, 1, tzinfo=UTC))
        self.assertEqual(shard_period('2007/13.jsonl', fallback), fallback)
        self.assertEqual(shard_period('whatever', fallback), fallback)

    def test_main_statements_have_set_based_plans(self):
        """Prints EXPLAIN for the PR description; guards against index-probe join plans."""
        load_listenbrainz_identity_evidence(SOURCE_VERSION, schemes=['spotify_track'])
        with connection.cursor() as cursor:
            cursor.execute(f'''
                CREATE UNLOGGED TABLE {RAW_STAGE_TABLE} (
                    subject_id uuid, value varchar(255), observation_count bigint, period timestamptz
                )
            ''')
            cursor.execute(f'''
                CREATE UNLOGGED TABLE {STAGE_TABLE} (
                    row_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
                    subject_id uuid NOT NULL,
                    value varchar(255) NOT NULL,
                    observation_count bigint NOT NULL,
                    shard_count integer NOT NULL,
                    first_seen timestamptz NOT NULL,
                    last_seen timestamptz NOT NULL
                )
            ''')
            statements = {
                'aggregate (raw -> ordered stage)': f'''
                    EXPLAIN INSERT INTO {STAGE_TABLE} (subject_id, value, observation_count, shard_count, first_seen, last_seen)
                    SELECT subject_id, value, SUM(observation_count), COUNT(*), MIN(period), MAX(period)
                    FROM {RAW_STAGE_TABLE} GROUP BY subject_id, value ORDER BY value, subject_id''',
                'apply batch (stage slice -> evidence)': 'EXPLAIN ' + APPLY_BATCH_SQL,
            }
            plans = {}
            for name, sql in statements.items():
                cursor.execute(sql, ['spotify_track', 'listenbrainz', SOURCE_VERSION, 0, 50000] if '%s' in sql else None)
                plans[name] = '\n'.join(row[0] for row in cursor.fetchall())
            cursor.execute(f'DROP TABLE {STAGE_TABLE}')
            cursor.execute(f'DROP TABLE {RAW_STAGE_TABLE}')
        for name, plan in plans.items():
            print(f'\nEXPLAIN {name}\n{plan}')
            self.assertNotIn('Nested Loop', plan, name)
            self.assertNotIn('mlcore_canonical_item', plan, f'{name}: no join against the item table')
        self.assertIn('Conflict Arbiter Indexes: mlcore_idev_unique', plans['apply batch (stage slice -> evidence)'])

    def test_command_loads_and_reports(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        call_command(
            'load_identity_evidence',
            '--source-version', SOURCE_VERSION,
            '--scheme', 'spotify_track',
            '--group-size', '3',
            '--batch-size', '2',
            '--work-mem', '64MB',
            '--staging-tablespace', 'juke_mlcore_cold',
            '--json',
            stdout=stdout, stderr=stderr,
        )
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload['groups_loaded'], 1)
        self.assertEqual(payload['evidence_row_count'], 4)
        self.assertIn('event=evidence_batch', stderr.getvalue())
        self.assertIn('event=evidence_group_complete', stderr.getvalue())
