import io
import json
import tempfile
import uuid
from pathlib import Path

from django.core.management import CommandError, call_command
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from mlcore.models import (
    CanonicalItem, CanonicalItemAlias, CanonicalItemRedirect, IdentityEvidence, MusicBrainzRecordingISRC,
)
from mlcore.services.canonical_items import identity_from_parts
from mlcore.services.spotify_clusters import apply_workspace, build_workspace, export_audit, export_review

SID = 'S' * 22
VERSION = 'fixture-mb'


class SpotifyClusterTests(TestCase):
    def item(self, typ='recording_msid', key=None):
        identity = identity_from_parts(item_type=typ, key_value=str(key or uuid.uuid4()))
        return CanonicalItem.objects.create(id=identity.item_id, item_type=identity.item_type,
                                            canonical_key=identity.canonical_key)

    def evidence(self, item, value=SID, n=2, scheme='spotify_track'):
        now = timezone.now()
        return IdentityEvidence.objects.create(subject_canonical_item=item, scheme=scheme, value=value,
                                               source='listenbrainz', source_version='fixture', observation_count=n,
                                               first_seen=now, last_seen=now)

    def edge(self, source, target):
        return CanonicalItemRedirect.objects.create(from_canonical_item=source, to_canonical_item=target,
                                                    source='fixture', source_version='fixture')

    def alias(self, owner, sid=SID, match_source='fixture'):
        return CanonicalItemAlias.objects.create(canonical_item=owner, source='spotify', resource_type='track',
                                                 source_id=sid, metadata={'match_source': match_source})

    def build(self, **kwargs):
        return build_workspace(sample_percent=kwargs.pop('sample_percent', 100), musicbrainz_version=VERSION,
                               progress=lambda x: None, **kwargs)

    def apply(self, **kwargs):
        return apply_workspace(source_version='fixture', progress=lambda x: None, **kwargs)

    def test_dominance_exact_boundary_and_minimum(self):
        low = self.item()
        self.evidence(low, n=1)
        mixed = self.item()
        self.evidence(mixed, n=8)
        self.evidence(mixed, 'T' * 22, 2)
        good = self.item()
        self.evidence(good, n=18)
        self.evidence(good, 'T' * 22, 2)
        self.assertEqual(self.build(), {'ready': 1})
        with connection.cursor() as c:
            c.execute('SELECT item_id, observations, total FROM tmp_sp_member')
            self.assertEqual(c.fetchall(), [(good.id, 18, 20)])

    def test_new_spotify_target_dry_run_replay_and_lean_evidence(self):
        a, b = self.item(), self.item()
        self.evidence(a)
        self.evidence(b)
        self.build()
        self.apply()
        self.assertEqual(CanonicalItem.objects.count(), 2)
        self.assertFalse(CanonicalItemRedirect.objects.exists())
        self.apply(write=True)
        target = CanonicalItem.objects.get(canonical_key='spotify_track:' + SID)
        self.assertEqual(set(CanonicalItemRedirect.objects.values_list('to_canonical_item_id', flat=True)), {target.id})
        self.assertEqual(CanonicalItemRedirect.objects.count(), 2)
        self.assertEqual(set(CanonicalItemRedirect.objects.first().evidence), {'algorithm', 'spotify_id'})
        self.assertEqual(CanonicalItemAlias.objects.get(source='spotify').canonical_item_id, target.id)
        self.build()
        result = self.apply(write=True)
        self.assertEqual(result['redirects'], 0)
        self.assertEqual(CanonicalItemRedirect.objects.count(), 2)
        self.assertEqual(CanonicalItemAlias.objects.count(), 1)

    def test_single_resolved_mbid_and_existing_redirect_unchanged(self):
        a, b, target = self.item(), self.item(), self.item('recording_mbid')
        old = self.edge(a, target)
        self.evidence(a)
        self.evidence(b)
        self.build()
        self.apply(write=True)
        old.refresh_from_db()
        self.assertEqual(old.source, 'fixture')
        self.assertEqual(old.to_canonical_item_id, target.id)
        self.assertEqual(CanonicalItemRedirect.objects.get(from_canonical_item=b).to_canonical_item_id, target.id)

    def test_b5_url_target(self):
        a, target = self.item(), self.item('recording_mbid')
        self.evidence(a)
        self.alias(target, match_source='musicbrainz_url')
        self.build()
        self.apply(write=True)
        self.assertEqual(CanonicalItemRedirect.objects.get(from_canonical_item=a).to_canonical_item_id, target.id)

    def test_unique_isrc_can_create_mbid_target(self):
        a = self.item()
        self.evidence(a)
        self.evidence(a, 'USAAA1200001', 3, 'isrc')
        mbid = uuid.uuid4()
        MusicBrainzRecordingISRC.objects.create(recording_mbid=mbid, isrc='USAAA1200001', source_version=VERSION)
        # Older releases cannot turn a unique current bridge into an ambiguity.
        MusicBrainzRecordingISRC.objects.create(recording_mbid=uuid.uuid4(), isrc='USAAA1200001', source_version='old')
        self.build()
        self.apply(write=True)
        target = CanonicalItem.objects.get(canonical_key='recording_mbid:' + str(mbid))
        self.assertEqual(CanonicalItemRedirect.objects.get(from_canonical_item=a).to_canonical_item_id, target.id)
        self.assertEqual(CanonicalItemAlias.objects.get(source='isrc').canonical_item_id, target.id)

    def test_ambiguous_isrc_falls_back_to_spotify(self):
        a = self.item()
        self.evidence(a)
        self.evidence(a, 'USAAA1200001', 3, 'isrc')
        for _ in range(2):
            MusicBrainzRecordingISRC.objects.create(recording_mbid=uuid.uuid4(), isrc='USAAA1200001', source_version=VERSION)
        self.build()
        self.apply(write=True)
        self.assertEqual(CanonicalItemRedirect.objects.get().to_canonical_item.item_type, 'spotify_track')

    def test_multiple_resolved_mbids_conflict(self):
        for _ in range(2):
            a = self.item()
            self.evidence(a)
            self.edge(a, self.item('recording_mbid'))
        self.assertEqual(self.build(), {'mbid_conflict': 1})
        self.assertEqual(self.apply(write=True)['processed'], 0)
        self.assertEqual(CanonicalItemRedirect.objects.count(), 2)

    def test_cross_source_mbid_disagreement_is_conflict(self):
        a = self.item()
        self.evidence(a)
        self.edge(a, self.item('recording_mbid'))
        self.alias(self.item('recording_mbid'), match_source='musicbrainz_url')
        self.assertEqual(self.build(), {'mbid_conflict': 1})

    def test_foreign_alias_and_retired_alias_never_overwritten(self):
        a = self.item()
        self.evidence(a)
        alias = self.alias(self.item())
        self.assertEqual(self.build(), {'alias_conflict': 1})
        self.apply(write=True)
        alias.refresh_from_db()
        self.assertFalse(CanonicalItemRedirect.objects.exists())
        alias.status = 'retired'
        alias.save()
        self.assertEqual(self.build(), {'alias_conflict': 1})

    def test_foreign_active_msid_redirect_is_conflict(self):
        a, other = self.item(), self.item()
        self.evidence(a)
        edge = self.edge(a, other)
        self.assertEqual(self.build(), {'redirect_conflict': 1})
        self.apply(write=True)
        edge.refresh_from_db()
        self.assertEqual(edge.to_canonical_item_id, other.id)

    def test_spotify_promotion_repoints_inbound_flat(self):
        root = self.item('spotify_track', SID)
        a, target = self.item(), self.item('recording_mbid')
        incoming = self.edge(a, root)
        self.evidence(a)
        self.alias(target, match_source='musicbrainz_url')
        self.build()
        self.apply(write=True)
        incoming.refresh_from_db()
        self.assertEqual(incoming.to_canonical_item_id, target.id)
        self.assertEqual(CanonicalItemRedirect.objects.get(from_canonical_item=root).to_canonical_item_id, target.id)
        self.assertFalse(CanonicalItemRedirect.objects.filter(to_canonical_item=root).exists())

    def test_cycles_are_skipped(self):
        a, b = self.item(), self.item()
        self.edge(a, b)
        self.edge(b, a)
        self.evidence(a)
        self.assertEqual(self.build(), {'redirect_depth': 1})

    def test_group_cap_review_export_and_bounded_audit(self):
        for _ in range(201):
            self.evidence(self.item())
        self.evidence(self.item(), 'A' * 22)
        self.assertEqual(self.build(), {'oversize': 1, 'ready': 1})
        with tempfile.TemporaryDirectory() as directory:
            audit, review = Path(directory) / 'audit.jsonl', Path(directory) / 'review.jsonl'
            self.assertEqual(export_audit(audit, limit=1), 1)
            export_review(review)
            row = json.loads(audit.read_text())
            self.assertIn('evidence', row)
            self.assertIn('listenbrainz_url', row)
            self.assertEqual(json.loads(review.read_text())['size'], 201)

    def test_sampling_is_deterministic_whole_group(self):
        for k in range(30):
            for _ in range(2):
                self.evidence(self.item(), f'{k:022d}')
        self.build(sample_percent=50)
        with connection.cursor() as c:
            c.execute('SELECT spotify_id, COUNT(*) FROM tmp_sp_member GROUP BY spotify_id ORDER BY spotify_id')
            first = c.fetchall()
        self.assertTrue(0 < len(first) < 30)
        self.assertTrue(all(n == 2 for _, n in first))
        self.build(sample_percent=50)
        with connection.cursor() as c:
            c.execute('SELECT spotify_id, COUNT(*) FROM tmp_sp_member GROUP BY spotify_id ORDER BY spotify_id')
            self.assertEqual(first, c.fetchall())

    def test_checkpoint_replay_and_gate(self):
        self.evidence(self.item())
        with tempfile.TemporaryDirectory() as d:
            args = ['--musicbrainz-version', VERSION, '--source-version', 'fixture', '--audit-export', d + '/a',
                    '--review-export', d + '/r', '--resume-state', d + '/s', '--sample-percent', '100']
            with self.assertRaises(CommandError):
                call_command('cluster_spotify_identity', *args, '--write', stdout=io.StringIO())
            call_command('cluster_spotify_identity', *args, '--write', '--owner-approved-full-run',
                         stdout=io.StringIO(), stderr=io.StringIO())
            state = json.loads(Path(d + '/s').read_text())
            self.assertTrue(state['after_key'])
            call_command('cluster_spotify_identity', *args, '--write', '--owner-approved-full-run',
                         stdout=io.StringIO(), stderr=io.StringIO())
            self.assertEqual(CanonicalItemRedirect.objects.count(), 1)
            self.assertEqual(len(Path(d + '/a').read_text().splitlines()), 1)
            with self.assertRaises(CommandError):
                call_command('cluster_spotify_identity', *args, '--sample-percent', '1', stdout=io.StringIO())

    def test_interrupted_after_commit_replays_safely(self):
        self.evidence(self.item())
        self.build()
        def crash(key):
            raise RuntimeError('simulated checkpoint failure after graph commit')
        with self.assertRaises(RuntimeError):
            self.apply(write=True, checkpoint=crash)
        self.build()
        self.apply(write=True)
        self.assertEqual(CanonicalItemRedirect.objects.count(), 1)
        self.assertEqual(CanonicalItemAlias.objects.count(), 1)

    def test_audit_metadata_supplement(self):
        a, target = self.item(), self.item('recording_mbid')
        self.evidence(a)
        self.alias(target, match_source='musicbrainz_url')
        self.build()
        with tempfile.TemporaryDirectory() as d:
            supplement = Path(d) / 'metadata.jsonl'
            supplement.write_text('\n'.join(json.dumps(dict(canonical_key=i.canonical_key,
                title='fixture title', artist='fixture artist', source='fixture dump')) for i in (a, target)))
            audit = Path(d) / 'audit.jsonl'
            self.assertEqual(export_audit(audit, metadata_path=supplement), 1)
            row = json.loads(audit.read_text())
            self.assertFalse(row['metadata_missing'])
            self.assertEqual(row['musicbrainz_metadata']['title'], 'fixture title')

    def test_isrc_alias_foreign_evidence_and_owner_are_preserved(self):
        a, outside = self.item(), self.item()
        self.evidence(a)
        for item in (a, outside):
            self.evidence(item, 'USAAA1200001', 3, 'isrc')
        owned = CanonicalItemAlias.objects.create(canonical_item=outside, source='isrc',
                                                  resource_type='recording', source_id='USAAA1200002')
        self.evidence(a, 'USAAA1200002', 3, 'isrc')
        self.build()
        self.apply(write=True)
        self.assertFalse(CanonicalItemAlias.objects.filter(source_id='USAAA1200001').exists())
        owned.refresh_from_db()
        self.assertEqual(owned.canonical_item_id, outside.id)

    def test_main_explains_use_hash_joins(self):
        self.evidence(self.item())
        plans = {}
        self.build(plans=plans)
        for name, lines in plans.items():
            plan = '\n'.join(lines)
            self.assertIn('Hash Join', plan, name)
            self.assertNotIn('Nested Loop', plan, name)
