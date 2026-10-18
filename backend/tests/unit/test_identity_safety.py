import uuid
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from mlcore.models import (
    CanonicalItem,
    CanonicalItemAlias,
    CanonicalItemRedirect,
    IdentityEvidence,
    MusicBrainzRecordingISRC,
    MusicBrainzRecordingMetadata,
    MusicBrainzRecordingURL,
    ProviderHydrationItem,
    ProviderHydrationRun,
    ListenBrainzMSIDMBIDMapping,
)
from mlcore.services import isrc_redirect_bridge, spotify_clusters, musicbrainz_url_aliases
from mlcore.services.canonical_items import identity_from_parts
from mlcore.services.identity_safety import HOLD_KEY
from mlcore.services.provider_hydration import SpotifyCandidate, hydrate_spotify_item, claim_hydration_item
from mlcore.services.recording_metadata import metadata_verdict

CODE = 'GBCFB0201305'
GOOD = 'USABC2600001'
VERSION = '20260627-002124'
SID = 'S' * 22
ALT = 'T' * 22


class MetadataChecks(SimpleTestCase):
    def check(self, title='Track', credit='Artist', candidate_title='Track', artists=('Artist',), duration=1000):
        reference = SimpleNamespace(title=title, artist_credit=credit, duration_ms=1000)
        candidate = SpotifyCandidate(SID, '', CODE, candidate_title, artists, duration, 1)
        return metadata_verdict(reference, candidate)

    def test_unicode_and_joined_complete_credits(self):
        self.assertEqual(self.check('Su Sızıyor', 'Altın Gün', 'Su Siziyor', ('Altin Gün',)), 'metadata_consistent')
        self.assertEqual(
            self.check(credit='Alok, Zeeba & Portugal. The Man', artists=('Alok', 'Zeeba', 'Portugal. The Man')), 'metadata_consistent'
        )
        self.assertEqual(self.check('Тоска', 'Artist', 'Другое'), 'recording_title_disagrees')

    def test_master_years_and_missing_context_are_not_erased(self):
        self.assertEqual(self.check('Track - 2008 Remaster', candidate_title='Track - 2011 Remaster'), 'version_context_disagrees')
        self.assertEqual(self.check('Track - Live', candidate_title='Track'), 'version_context_disagrees')

    def test_partial_credit_missing_metadata_and_duration_conflict(self):
        self.assertEqual(self.check(credit='Alok, Zeeba', artists=('Alok',)), 'recording_artist_disagrees')
        self.assertEqual(self.check(credit=''), 'missing_recording_metadata')
        self.assertEqual(self.check(credit='And Also the Trees', artists=('Also the Trees',)), 'recording_artist_disagrees')
        self.assertEqual(self.check(duration=10000), 'recording_duration_disagrees')


class IdentitySafetyTests(TestCase):
    def item(self, kind='recording_msid'):
        identity = identity_from_parts(item_type=kind, key_value=str(uuid.uuid4()))
        return CanonicalItem.objects.create(id=identity.item_id, item_type=kind, canonical_key=identity.canonical_key)

    def alias(self, item, source='isrc', value=CODE, status='conflict', metadata=None):
        return CanonicalItemAlias.objects.create(
            canonical_item=item,
            source=source,
            resource_type='track' if source == 'spotify' else 'recording',
            source_id=value,
            status=status,
            metadata=metadata or {},
        )

    def evidence(self, item, scheme, value, n=2):
        return IdentityEvidence.objects.create(
            subject_canonical_item=item,
            scheme=scheme,
            value=value,
            source='listenbrainz',
            source_version='fixture',
            observation_count=n,
            first_seen=timezone.now(),
            last_seen=timezone.now(),
        )

    def mbfact(self, item, code=CODE):
        return MusicBrainzRecordingISRC.objects.create(recording_mbid=item.canonical_key.split(':')[1], source_version=VERSION, isrc=code)

    def hydration(self, reference=True):
        item = self.item('recording_mbid')
        self.mbfact(item)
        if reference:
            MusicBrainzRecordingMetadata.objects.create(
                recording_mbid=item.canonical_key.split(':')[1],
                source_version=VERSION,
                title='Track',
                artist_credit='Artist',
                source_checksum='a' * 64,
                duration_ms=1000,
            )
        queue = ProviderHydrationItem.objects.create(
            canonical_item=item, provider='spotify', identifier_type='isrc', identifier=CODE, source_version=VERSION
        )
        run = ProviderHydrationRun.objects.create(provider='spotify')
        client = mock.Mock()
        client.search_isrc.return_value = [SpotifyCandidate(SID, 'spotify:track:' + SID, CODE, 'Track', ('Artist',), 1000, 1)]
        return item, queue, run, client

    def test_missing_metadata_spends_no_api_request(self):
        item, queue, run, client = self.hydration(reference=False)
        self.assertEqual(hydrate_spotify_item(queue, run=run, client=client), 'ambiguous')
        client.search_isrc.assert_not_called()
        run.refresh_from_db()
        self.assertEqual(run.request_count, 0)
        self.assertEqual(run.ambiguous_count, 1)
        self.assertFalse(CanonicalItemAlias.objects.exists())

    def test_same_owner_conflict_or_annotation_is_never_reactivated(self):
        item, queue, run, client = self.hydration()
        alias = self.alias(item, 'spotify', SID)
        self.assertEqual(hydrate_spotify_item(queue, run=run, client=client), 'ambiguous')
        alias.refresh_from_db()
        self.assertEqual(alias.status, 'conflict')
        alias.status = 'active'
        alias.metadata = {HOLD_KEY: {'reason': 'operator'}}
        alias.save()
        self.assertEqual(hydrate_spotify_item(queue, run=run, client=client), 'ambiguous')
        alias.refresh_from_db()
        self.assertIn(HOLD_KEY, alias.metadata)

    def test_isrc_conflict_or_queue_annotation_prevents_claim_and_provider_call(self):
        item, queue, run, client = self.hydration()
        self.alias(item)
        self.assertIsNone(claim_hydration_item(run=run, worker_id='test'))
        self.assertEqual(hydrate_spotify_item(queue, run=run, client=client), 'ambiguous')
        client.search_isrc.assert_not_called()
        CanonicalItemAlias.objects.all().delete()
        queue.status = 'pending'
        queue.evidence = {HOLD_KEY: {'reason': 'operator'}}
        queue.save()
        self.assertIsNone(claim_hydration_item(run=run, worker_id='test'))

    def test_wrong_reference_is_durably_held_and_raw_fact_remains(self):
        item, queue, run, client = self.hydration()
        alias = self.alias(item, status='active')
        client.search_isrc.return_value = [SpotifyCandidate(SID, '', CODE, 'Leisure Lakes', ('Super Numeri',), 1000, 1)]
        self.assertEqual(hydrate_spotify_item(queue, run=run, client=client), 'ambiguous')
        queue.refresh_from_db()
        alias.refresh_from_db()
        self.assertIn(HOLD_KEY, queue.evidence)
        self.assertEqual(alias.status, 'conflict')
        self.assertEqual(MusicBrainzRecordingISRC.objects.count(), 1)
        self.assertFalse(CanonicalItemAlias.objects.filter(source='spotify').exists())

    def test_hold_arriving_during_provider_request_is_rechecked(self):
        item, queue, run, client = self.hydration()

        def response(_code):
            self.alias(item)
            return [SpotifyCandidate(SID, '', CODE, 'Track', ('Artist',), 1000, 1)]

        client.search_isrc.side_effect = response
        self.assertEqual(hydrate_spotify_item(queue, run=run, client=client), 'ambiguous')
        self.assertFalse(CanonicalItemAlias.objects.filter(source='spotify').exists())

    def test_positive_metadata_creates_validated_alias(self):
        item, queue, run, client = self.hydration()
        self.assertEqual(hydrate_spotify_item(queue, run=run, client=client), 'matched')
        self.assertEqual(CanonicalItemAlias.objects.get(source='spotify').metadata['metadata_validation']['verdict'], 'metadata_consistent')

    def test_isrc_bridge_held_member_vetoes_whole_existing_cluster(self):
        mbid = self.item('recording_mbid')
        self.mbfact(mbid, GOOD)
        self.mbfact(mbid)
        root = self.item('spotify_track')
        good = self.item()
        held = self.item()
        self.evidence(good, 'isrc', GOOD)
        self.evidence(held, 'isrc', CODE)
        self.alias(mbid)
        for member in [good, held]:
            CanonicalItemRedirect.objects.create(
                from_canonical_item=member, to_canonical_item=root, source='fixture', source_version='fixture'
            )
        state = isrc_redirect_bridge.build_workspace(VERSION)
        self.assertEqual(state.root_status.get('quarantined_reference'), 1)
        isrc_redirect_bridge.apply_redirect_batch(source_version=VERSION, last_root=None, batch_size=10, write=True)
        self.assertEqual(CanonicalItemRedirect.objects.count(), 2)

    def test_spotify_cluster_held_isrc_member_vetoes_group(self):
        mbid = self.item('recording_mbid')
        self.mbfact(mbid)
        self.alias(mbid)
        for code in [GOOD, CODE]:
            member = self.item()
            self.evidence(member, 'spotify_track', SID)
            self.evidence(member, 'isrc', code)
        state = spotify_clusters.build_workspace(sample_percent=100, musicbrainz_version=VERSION, progress=lambda _: None)
        self.assertEqual(state, {'quarantined_reference': 1})
        spotify_clusters.apply_workspace(write=True, source_version='fixture', progress=lambda _: None)
        self.assertFalse(CanonicalItemRedirect.objects.exists())

    def test_new_hold_invalidates_staged_spotify_write(self):
        member = self.item()
        self.evidence(member, 'spotify_track', SID)
        spotify_clusters.build_workspace(sample_percent=100, musicbrainz_version=VERSION, progress=lambda _: None)
        self.alias(member, 'spotify', SID)
        with self.assertRaisesRegex(ValueError, 'holds changed'):
            spotify_clusters.apply_workspace(write=True, source_version='fixture', progress=lambda _: None)
        self.assertFalse(CanonicalItemRedirect.objects.exists())

    def test_new_hold_invalidates_staged_isrc_write(self):
        mbid = self.item('recording_mbid')
        self.mbfact(mbid)
        member = self.item()
        self.evidence(member, 'isrc', CODE)
        isrc_redirect_bridge.build_workspace(VERSION)
        self.alias(mbid)
        with self.assertRaisesRegex(ValueError, 'holds changed'):
            isrc_redirect_bridge.apply_redirect_batch(source_version=VERSION, last_root=None, batch_size=10, write=True)
        self.assertFalse(CanonicalItemRedirect.objects.exists())

    def test_benchmark_keeps_held_comparisons_out_of_success_numerator(self):
        item = self.item('recording_mbid')
        self.mbfact(item)
        mbid = item.canonical_key.split(':')[1]
        self.alias(item, 'spotify', SID, 'active', {'match_source': 'isrc', 'match_isrc': CODE})
        self.alias(item)
        MusicBrainzRecordingURL.objects.create(
            recording_mbid=mbid,
            provider='spotify',
            url='https://open.spotify.com/track/' + ALT,
            url_fingerprint='held',
            source_version=VERSION,
            link_type_id=1,
        )
        musicbrainz_url_aliases.build_workspace(VERSION)
        report = musicbrainz_url_aliases.precision_report()
        self.assertEqual(report['compared'], 0)
        self.assertEqual(report['held_comparisons'], 1)
        self.assertEqual(report['population'], 1)
        self.assertEqual(report['precision'], 0)
        self.assertIsNone(report['eligible_reference_agreement'])

    def test_benchmark_excludes_quarantined_saved_candidates(self):
        item = self.item('recording_mbid')
        self.mbfact(item)
        mbid = item.canonical_key.split(':')[1]
        self.alias(item, 'spotify', SID, 'active', {'match_source': 'isrc'})
        ProviderHydrationItem.objects.create(
            canonical_item=item,
            provider='spotify',
            identifier_type='isrc',
            identifier=CODE,
            status='ambiguous',
            evidence={HOLD_KEY: {'reason': 'operator'}, 'candidates': [{'track_id': ALT}]},
        )
        MusicBrainzRecordingURL.objects.create(
            recording_mbid=mbid,
            provider='spotify',
            url='https://open.spotify.com/track/' + ALT,
            url_fingerprint='candidate',
            source_version=VERSION,
            link_type_id=1,
        )
        musicbrainz_url_aliases.build_workspace(VERSION)
        report = musicbrainz_url_aliases.precision_report()
        self.assertEqual(report['different_same_isrc'], 0)
        self.assertEqual(report['different'], 1)

    def test_raw_alias_materializer_honors_queue_only_quarantine(self):
        from mlcore.services.musicbrainz_isrc_aliases import materialize_musicbrainz_isrc_alias_batch

        item, queue, run, client = self.hydration()
        queue.evidence = {HOLD_KEY: {'reason': 'operator'}}
        queue.save()
        result = materialize_musicbrainz_isrc_alias_batch(source_version=VERSION, last_isrc=None, batch_size=10)
        self.assertEqual(result.created_count, 0)
        self.assertFalse(CanonicalItemAlias.objects.exists())

    def test_legacy_mbid_bridge_does_not_bypass_a_held_member(self):
        from mlcore.services.listenbrainz_identity_bridge import _classify_and_materialize

        source = self.item()
        target = self.item('recording_mbid')
        self.evidence(source, 'isrc', CODE)
        self.alias(target)
        ListenBrainzMSIDMBIDMapping.objects.create(
            recording_msid=source.canonical_key.split(':')[1],
            recording_mbid=target.canonical_key.split(':')[1],
            source_version='fixture',
            first_shard='1',
            last_shard='1',
        )
        _classify_and_materialize('fixture')
        self.assertFalse(CanonicalItemRedirect.objects.exists())

    def test_metadata_from_another_release_does_not_authorize_hydration(self):
        item, queue, run, client = self.hydration()
        MusicBrainzRecordingMetadata.objects.update(source_version='another-version')
        self.assertEqual(hydrate_spotify_item(queue, run=run, client=client), 'ambiguous')
        client.search_isrc.assert_not_called()

    def test_serving_treats_an_annotated_active_alias_as_conflict(self):
        # Execute the actual serving SQL; this does not depend on optional FastAPI imports.
        import ast
        from pathlib import Path
        from django.db import connection

        tree = ast.parse((Path(__file__).parents[2] / 'recommender_engine/app/main.py').read_text())
        query = next(
            ast.literal_eval(n.value)
            for n in tree.body
            if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == '_RESOLVE_ALIASES_SQL' for t in n.targets)
        )
        item = self.item('recording_mbid')
        self.alias(item, 'spotify', SID, 'active', {HOLD_KEY: {'reason': 'operator'}})
        with connection.cursor() as cursor:
            cursor.execute(query, [['spotify'], ['track'], [SID]])
            row = cursor.fetchone()
        self.assertEqual(row[3], 'conflict')

    def test_direct_redirect_writer_honors_holds_and_does_not_reactivate(self):
        from mlcore.services.canonical_redirects import upsert_canonical_redirect

        member = self.item()
        target = self.item('recording_mbid')
        edge = CanonicalItemRedirect.objects.create(
            from_canonical_item=member, to_canonical_item=target, status='retired', source='fixture', source_version='fixture'
        )
        upsert_canonical_redirect(from_item_id=member.id, to_item_id=target.id, source='test', source_version='test')
        edge.refresh_from_db()
        self.assertEqual(edge.status, 'retired')
        self.evidence(member, 'isrc', CODE)
        self.alias(target)
        with self.assertRaisesRegex(ValueError, 'quarantined'):
            upsert_canonical_redirect(from_item_id=member.id, to_item_id=target.id, source='test', source_version='test')
