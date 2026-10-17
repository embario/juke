import csv
import io
import json
import tempfile
import uuid
from pathlib import Path
from unittest.mock import patch

from django.core.management import CommandError, call_command
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from mlcore.models import (
    CanonicalAliasMaterializationRun,
    CanonicalItem,
    CanonicalItemRedirect,
    IdentityEvidence,
    MusicBrainzRecordingISRC,
    ListenBrainzMSIDMBIDMapping,
    SourceIngestionRun,
)
from mlcore.services.canonical_items import identity_from_parts
from mlcore.services.isrc_redirect_bridge import (
    REDIRECT_SOURCE,
    apply_redirect_batch,
    build_workspace,
)

VERSION = 'mb-isrc-test-v1'


def _redirect(source, target, origin='listenbrainz-identity-bridge'):
    return CanonicalItemRedirect.objects.create(
        from_canonical_item=source, to_canonical_item=target, source=origin, source_version='t', status='active',
    )


class ISRCRedirectBridgeTests(TestCase):
    def setUp(self):
        SourceIngestionRun.objects.create(
            source='musicbrainz-identity-bridge', import_mode='full', source_version=VERSION,
            raw_path='/tmp/mb', checksum='c', status='succeeded',
        )
        self.mbid = {name: uuid.uuid4() for name in ('M1', 'M2', 'M3', 'M4', 'M5', 'M6')}
        self.mb_items = {name: self._item('recording_mbid', self.mbid[name]) for name in ('M1', 'M2', 'M6')}
        MusicBrainzRecordingISRC.objects.bulk_create([
            MusicBrainzRecordingISRC(recording_mbid=self.mbid[mbid], isrc=isrc, source_version=version)
            for mbid, isrc, version in (
                ('M1', 'I1', VERSION), ('M1', 'I2', VERSION), ('M2', 'I3', VERSION),
                ('M3', 'I4', VERSION), ('M4', 'I4', VERSION),  # I4 is ambiguous in MusicBrainz
                ('M5', 'I5', VERSION),  # M5 has no canonical item
                ('M6', 'I6', VERSION),
                ('M2', 'I1', 'mb-old'),  # an older version must not make I1 ambiguous
            )
        ])
        names = ['S1', 'S2', 'S3', 'S4', 'S5', 'S6', 'S8', 'S9', 'S10', 'S11']
        self.msid = {name: self._item('recording_msid', uuid.uuid4()) for name in names}
        self.missing_subject = uuid.uuid4()
        _redirect(self.msid['S5'], self.mb_items['M1'])
        _redirect(self.msid['S6'], self.mb_items['M2'])
        # Cluster C (spotify_track root) with two MSIDs; only S8 carries an ISRC.
        self.cluster = self._item('spotify_track', 'C' * 22)
        _redirect(self.msid['S8'], self.cluster, origin='listenbrainz-spotify-cluster')
        _redirect(self.msid['S9'], self.cluster, origin='listenbrainz-spotify-cluster')
        # Cluster D whose members disagree.
        self.cluster_d = self._item('spotify_track', 'D' * 22)
        _redirect(self.msid['S10'], self.cluster_d, origin='listenbrainz-spotify-cluster')
        _redirect(self.msid['S11'], self.cluster_d, origin='listenbrainz-spotify-cluster')

        evidence = [
            (self.msid['S1'].id, 'I1'), (self.msid['S1'].id, 'I2'),
            (self.msid['S2'].id, 'I1'), (self.msid['S2'].id, 'I3'),
            (self.msid['S3'].id, 'I4'),
            (self.msid['S4'].id, 'I5'),
            (self.msid['S5'].id, 'I1'),
            (self.msid['S6'].id, 'I1'),
            (self.missing_subject, 'I2'),
            (self.msid['S8'].id, 'I6'),
            (self.msid['S10'].id, 'I1'), (self.msid['S11'].id, 'I3'),
            (self.mb_items['M2'].id, 'I3'),  # an MBID subject is not bridged
        ]
        now = timezone.now()
        IdentityEvidence.objects.bulk_create([
            IdentityEvidence(
                subject_canonical_item_id=subject, scheme='isrc', value=value, source='listenbrainz',
                source_version='lb-v3', observation_count=3, shard_count=1, first_seen=now, last_seen=now,
            )
            for subject, value in evidence
        ] + [
            IdentityEvidence(
                subject_canonical_item_id=self.msid['S9'].id, scheme='spotify_track', value='I1',
                source='listenbrainz', source_version='lb-v3', first_seen=now, last_seen=now,
            ),
        ])

    @staticmethod
    def _item(item_type, key):
        identity = identity_from_parts(item_type=item_type, key_value=key)
        return CanonicalItem.objects.create(
            id=identity.item_id, item_type=identity.item_type, canonical_key=identity.canonical_key,
        )

    def _run(self, *args):
        out = io.StringIO()
        call_command('bridge_isrc_redirects', *args, stdout=out, stderr=io.StringIO())
        return json.loads(out.getvalue())

    def _target_of(self, item):
        return CanonicalItemRedirect.objects.get(from_canonical_item=item).to_canonical_item_id

    def test_classifies_subjects_and_roots(self):
        workspace = build_workspace(VERSION)
        self.assertEqual(workspace.unambiguous_isrcs, 5)  # I1, I2, I3, I5, I6
        self.assertEqual(
            workspace.subject_status,
            {
                'candidate': 4,  # S1, S8 (via cluster C), S10, S11 (cluster D)
                'multiple_mbids': 1,  # S2
                'target_missing': 1,  # S4
                'already_same_mbid': 1,  # S5
                'already_other_mbid': 1,  # S6
                'subject_missing': 1,
                'not_msid': 1,  # the MBID subject
            },
        )
        self.assertEqual(workspace.root_status, {'new': 2, 'cluster_conflict': 1, 'multiple_mbids': 1, 'target_missing': 1})
        self.assertEqual(workspace.inbound_redirects, 2)  # S8 and S9 point at cluster C

    def test_dry_run_writes_nothing(self):
        before = list(CanonicalItemRedirect.objects.values_list('from_canonical_item_id', 'to_canonical_item_id'))
        payload = self._run('--json')
        self.assertEqual(payload['mode'], 'dry-run')
        self.assertEqual(payload['redirects_would_insert'], 2)
        self.assertEqual(payload['inbound_would_repoint'], 2)
        after = list(CanonicalItemRedirect.objects.values_list('from_canonical_item_id', 'to_canonical_item_id'))
        self.assertEqual(sorted(before), sorted(after))
        self.assertEqual(CanonicalAliasMaterializationRun.objects.count(), 0)

    def test_full_write_requires_explicit_approval(self):
        with self.assertRaises(CommandError):
            self._run('--write')
        self.assertFalse(CanonicalItemRedirect.objects.filter(source=REDIRECT_SOURCE).exists())

    def test_write_is_flat_and_never_changes_existing_redirects(self):
        payload = self._run('--write', '--full-run-approved', '--json')
        self.assertEqual(payload['redirects_inserted'], 2)
        self.assertEqual(payload['inbound_repointed'], 2)
        m1, m2, m6 = (self.mb_items[name].id for name in ('M1', 'M2', 'M6'))
        self.assertEqual(self._target_of(self.msid['S1']), m1)
        new = CanonicalItemRedirect.objects.get(from_canonical_item=self.msid['S1'])
        self.assertEqual(new.source, REDIRECT_SOURCE)
        self.assertEqual(new.evidence['recording_mbid'], str(self.mbid['M1']))
        self.assertEqual(new.evidence['isrcs'], ['I1', 'I2'])
        # The cluster root moves and its members are repointed straight at the MBID (one hop).
        self.assertEqual(self._target_of(self.cluster), m6)
        self.assertEqual(self._target_of(self.msid['S8']), m6)
        self.assertEqual(self._target_of(self.msid['S9']), m6)
        self.assertEqual(
            CanonicalItemRedirect.objects.get(from_canonical_item=self.msid['S9']).evidence['repointed_from'],
            str(self.cluster.id),
        )
        # Existing edges are untouched; ambiguous cases get nothing.
        self.assertEqual(self._target_of(self.msid['S6']), m2)
        self.assertEqual(self._target_of(self.msid['S5']), m1)
        self.assertEqual(self._target_of(self.msid['S10']), self.cluster_d.id)
        for name in ('S2', 'S3', 'S4'):
            self.assertFalse(CanonicalItemRedirect.objects.filter(from_canonical_item=self.msid[name]).exists())
        self.assertFalse(CanonicalItemRedirect.objects.filter(from_canonical_item=self.cluster_d).exists())
        self.assertFalse(CanonicalItemRedirect.objects.filter(from_canonical_item=self.mb_items['M2']).exists())

    def test_rerun_is_idempotent(self):
        self._run('--write', '--full-run-approved', '--json')
        before = CanonicalItemRedirect.objects.count()
        payload = self._run('--write', '--full-run-approved', '--json')
        self.assertEqual(payload['redirects_inserted'], 0)
        self.assertEqual(payload['inbound_repointed'], 0)
        self.assertEqual(CanonicalItemRedirect.objects.count(), before)

    def test_redirect_written_after_staging_is_not_overwritten(self):
        build_workspace(VERSION)
        _redirect(self.msid['S1'], self.mb_items['M2'], origin='someone-else')
        result = apply_redirect_batch(source_version=VERSION, last_root=None, batch_size=10, write=True)
        self.assertEqual(result.inserted, 1)  # only the cluster root
        self.assertEqual(self._target_of(self.msid['S1']), self.mb_items['M2'].id)

    def test_batches_resume_with_the_stored_sample(self):
        first = self._run('--write', '--full-run-approved', '--batch-size', '1', '--max-batches', '1', '--json')
        self.assertEqual(first['status'], 'paused')
        self.assertEqual(first['redirects_inserted'], 1)
        run = CanonicalAliasMaterializationRun.objects.get(pk=first['run_id'])
        self.assertEqual(run.checkpoints['sample_percent'], 100.0)
        with self.assertRaises(CommandError):
            self._run('--write', '--resume-run-id', first['run_id'], '--sample-percent', '1')
        second = self._run('--write', '--full-run-approved', '--resume-run-id', first['run_id'], '--json')
        self.assertEqual(second['status'], 'complete')
        self.assertEqual(second['redirects_inserted'], 2)
        self.assertEqual(self._target_of(self.msid['S9']), self.mb_items['M6'].id)

    def test_sample_write_is_allowed_without_full_approval_and_is_a_subset(self):
        payload = self._run('--write', '--sample-percent', '0.01', '--json')
        self.assertEqual(payload['sample_percent'], 0.01)
        self.assertLessEqual(payload['subjects'], 13)
        self.assertLessEqual(payload['redirects_inserted'], 2)
        run = CanonicalAliasMaterializationRun.objects.get(pk=payload['run_id'])
        self.assertEqual(run.checkpoints['sample_percent'], 0.01)
        with self.assertRaises(ValueError):
            build_workspace(VERSION, sample_percent=0)

    def test_audit_export_has_metadata_for_each_merge(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'audit.csv'
            payload = self._run('--write', '--full-run-approved', '--audit-path', str(path), '--json')
            rows = list(csv.DictReader(path.open()))
        self.assertEqual(payload['audit_rows'], 2)
        by_root = {row['root_id']: row for row in rows}
        s1 = by_root[str(self.msid['S1'].id)]
        self.assertEqual(s1['recording_mbid'], str(self.mbid['M1']))
        self.assertEqual(s1['musicbrainz_url'], f'https://musicbrainz.org/recording/{self.mbid["M1"]}')
        self.assertEqual(s1['isrcs'], 'I1 I2')
        self.assertEqual(sorted(s1['musicbrainz_isrcs'].split()), ['I1', 'I2'])
        self.assertTrue(s1['member_msids'])
        self.assertEqual(s1['redirect_written'], 'yes')
        cluster = by_root[str(self.cluster.id)]
        self.assertEqual(cluster['root_type'], 'spotify_track')
        self.assertIn(self.msid['S8'].canonical_key.split(':')[1], cluster['member_msids'])

    def test_explain_covers_main_statements(self):
        workspace = build_workspace(VERSION, explain_plans=True)
        self.assertEqual(
            set(workspace.explains),
            {'stage_isrcs', 'stage_subjects', 'redirect_hop', 'item_types', 'stage_inbound', 'write_redirects'},
        )
        write_plan = '\n'.join(workspace.explains['write_redirects'])
        self.assertIn('Hash Join', write_plan)
        self.assertNotIn('Nested Loop', write_plan)
        print('\nEXPLAIN B7 insert/repoint (small fixture)\n' + write_plan)

    def test_exact_counts_are_persisted_and_exported(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'audit.csv'
            self._run('--write', '--full-run-approved', '--audit-path', str(path), '--json')
            with path.open() as handle:
                row = next(row for row in csv.DictReader(handle) if row['root_id'] == str(self.msid['S1'].id))
        edge = CanonicalItemRedirect.objects.get(from_canonical_item=self.msid['S1'])
        self.assertEqual((edge.evidence['subject_count'], edge.evidence['observation_count']), (1, 6))
        self.assertEqual((row['subject_count'], row['observation_count']), ('1', '6'))

    def test_mixed_rejected_members_veto_cluster(self):
        for rejected in ('S2', 'S4'):
            with self.subTest(member=rejected):
                edge = _redirect(self.msid[rejected], self.cluster)
                before = list(CanonicalItemRedirect.objects.order_by('pk').values_list(
                    'from_canonical_item_id', 'to_canonical_item_id'))
                build_workspace(VERSION)
                apply_redirect_batch(source_version=VERSION, last_root=None, batch_size=100, write=True)
                self.assertFalse(CanonicalItemRedirect.objects.filter(from_canonical_item=self.cluster).exists())
                for from_id, to_id in before:
                    self.assertEqual(CanonicalItemRedirect.objects.get(from_canonical_item_id=from_id).to_canonical_item_id, to_id)
                edge.delete()

    def test_conflicting_cluster_is_rejected_even_when_only_one_subject_hash_is_sampled(self):
        # Select deterministic subject keys straddling 1%; the old per-subject filter accepted A alone.
        identities = [identity_from_parts(item_type='recording_msid', key_value=uuid.UUID(int=n + 10000))
                      for n in range(2000)]
        with connection.cursor() as cursor:
            cursor.execute('SELECT id::text, mod(abs(hashtext(id::text)::bigint), 10000) '
                           'FROM unnest(%s::uuid[]) ids(id)', [[str(item.item_id) for item in identities]])
            buckets = dict(cursor.fetchall())
        selected = {}
        for identity in identities:
            inside = buckets[str(identity.item_id)] < 100
            if inside not in selected:
                selected[inside] = self._item('recording_msid', identity.canonical_key.split(':')[1])
        self.assertEqual(len(selected), 2)
        CanonicalItemRedirect.objects.filter(to_canonical_item=self.cluster_d).delete()
        for item, isrc in ((selected[True], 'I1'), (selected[False], 'I3')):
            _redirect(item, self.cluster_d)
            IdentityEvidence.objects.create(subject_canonical_item_id=item.id, scheme='isrc', value=isrc,
                                            source='listenbrainz', source_version='t',
                                            first_seen=timezone.now(), last_seen=timezone.now())
        full = build_workspace(VERSION)
        sample = build_workspace(VERSION, sample_percent=1)
        self.assertEqual(full.root_status['cluster_conflict'], sample.root_status['cluster_conflict'])
        apply_redirect_batch(source_version=VERSION, last_root=None, batch_size=100, write=True)
        self.assertFalse(CanonicalItemRedirect.objects.filter(from_canonical_item=self.cluster_d).exists())
        for item in selected.values():
            self.assertEqual(self._target_of(item), self.cluster_d.id)

    def test_gate_uses_effective_percentage_on_new_and_resumed_writes(self):
        self._run('--write', '--sample-percent', '1', '--json')
        for percent in ('50', '99.999', '100'):
            with self.subTest(percent=percent), self.assertRaises(CommandError):
                self._run('--write', '--sample-percent', percent, '--json')
        first = self._run('--write', '--full-run-approved', '--batch-size', '1', '--max-batches', '1', '--json')
        with self.assertRaises(CommandError):
            self._run('--write', '--resume-run-id', first['run_id'], '--json')

    def test_spotify_root_audit_contains_member_mapping(self):
        msid = self.msid['S8'].canonical_key.split(':')[1]
        ListenBrainzMSIDMBIDMapping.objects.create(
            recording_msid=msid, recording_mbid=self.mbid['M6'], source_version='t', status='active')
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'audit.csv'
            self._run('--audit-path', str(path), '--json')
            with path.open() as handle:
                row = next(row for row in csv.DictReader(handle) if row['root_id'] == str(self.cluster.id))
        self.assertIn(msid, row['member_msids'])
        self.assertIn(f'{msid}={self.mbid["M6"]}:active', row['listenbrainz_mapped_mbids'])
        self.assertEqual(row['inbound_redirects'], '2')

    def test_audit_survives_pause_resume_and_completed_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'audit.csv'
            first = self._run('--write', '--full-run-approved', '--batch-size', '1', '--max-batches', '1',
                              '--audit-path', str(path), '--json')
            with path.open() as handle:
                paused = list(csv.DictReader(handle))
            self.assertEqual(sorted(row['redirect_written'] for row in paused), ['no', 'yes'])
            self._run('--write', '--full-run-approved', '--resume-run-id', first['run_id'],
                      '--audit-path', str(path), '--json')
            with path.open() as handle:
                resumed = list(csv.DictReader(handle))
            self.assertEqual({row['root_id'] for row in paused}, {row['root_id'] for row in resumed})
            self.assertEqual([row['redirect_written'] for row in resumed], ['yes', 'yes'])
            self._run('--export-audit-run-id', first['run_id'], '--audit-path', str(path), '--json')
            with path.open() as handle:
                self.assertEqual(resumed, list(csv.DictReader(handle)))

    def test_checkpoint_failure_rolls_back_redirect_batch(self):
        original_save = CanonicalAliasMaterializationRun.save

        def fail_checkpoint(run, *args, **kwargs):
            if run.status == 'running' and run.processed_items:
                raise RuntimeError('checkpoint failed')
            return original_save(run, *args, **kwargs)

        with patch.object(CanonicalAliasMaterializationRun, 'save', fail_checkpoint):
            with self.assertRaisesRegex(RuntimeError, 'checkpoint failed'):
                self._run('--write', '--full-run-approved', '--json')
        self.assertFalse(CanonicalItemRedirect.objects.filter(source=REDIRECT_SOURCE).exists())
        run = CanonicalAliasMaterializationRun.objects.get()
        run.refresh_from_db()
        self.assertEqual(run.processed_items, 0)
        self.assertEqual(len(run.checkpoints['audit_rows']), 2)
        resumed = self._run('--write', '--full-run-approved', '--resume-run-id', str(run.id), '--json')
        self.assertEqual(resumed['redirects_inserted'], 2)
