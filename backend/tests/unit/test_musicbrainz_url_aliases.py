import io
import json
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from mlcore.models import (
    CanonicalAliasMaterializationRun,
    CanonicalItem,
    CanonicalItemAlias,
    CanonicalItemRedirect,
    MusicBrainzRecordingURL,
    ProviderHydrationItem,
    SourceIngestionRun,
)
from mlcore.services.canonical_items import identity_from_parts
from mlcore.services.musicbrainz_url_aliases import (
    build_workspace,
    latest_musicbrainz_url_source_version,
)

VERSION = 'mb-test-v1'
ID_A, ID_B1, ID_B2 = 'A' * 22, 'B' * 21 + '1', 'B' * 21 + '2'
ID_D, ID_F, ID_SHARED = 'D' * 22, 'F' * 22, 'S' * 22
ID_J_MB, ID_J_API = 'J' * 22, 'j' * 22
ID_K = 'K' * 22
ID_L_MB, ID_L_API = 'L' * 22, 'l' * 22
ID_OTHER = 'O' * 22


def mbid():
    return uuid.uuid4()


class MusicBrainzURLAliasTests(TestCase):
    def setUp(self):
        SourceIngestionRun.objects.create(
            source='musicbrainz-identity-bridge', import_mode='full', source_version=VERSION,
            raw_path='/tmp/mb', checksum='c', status='succeeded',
        )
        self.mb = {name: mbid() for name in 'A B C D F H I J K L'.split()}
        self.items = {name: self._item(self.mb[name]) for name in 'A B D F H I J K L'.split()}
        # D is redirected onto a target E (final), which has its own MBID item.
        self.target_e = self._item(mbid())
        CanonicalItemRedirect.objects.create(
            from_canonical_item=self.items['D'], to_canonical_item=self.target_e,
            source='test', source_version='t', status='active',
        )
        # F's Spotify ID is already owned by an unrelated item.
        self.owner_other = self._item(mbid())
        CanonicalItemAlias.objects.create(
            canonical_item=self.owner_other, source='spotify', resource_type='track', source_id=ID_F,
            metadata={'match_source': 'isrc'},
        )
        # J, K, L carry API-hydrated aliases to compare against.
        for name, spotify_id in (('J', ID_J_API), ('K', ID_K), ('L', ID_L_API)):
            CanonicalItemAlias.objects.create(
                canonical_item=self.items[name], source='spotify', resource_type='track', source_id=spotify_id,
                metadata={'match_source': 'isrc'},
            )
        ProviderHydrationItem.objects.create(
            canonical_item=self.items['L'], provider='spotify', identifier_type='isrc', identifier='USL',
            status='ambiguous', evidence={'candidates': [{'track_id': ID_L_API}, {'track_id': ID_L_MB}]},
        )

        urls = [
            (self.mb['A'], f'https://open.spotify.com/intl-es/track/{ID_A}?si=abc'),
            (self.mb['A'], 'https://open.spotify.com/artist/' + 'Z' * 22),
            (self.mb['B'], f'https://open.spotify.com/track/{ID_B1}'),
            (self.mb['B'], f'spotify:track:{ID_B2}'),
            (self.mb['C'], f'https://open.spotify.com/track/{"C" * 22}'),
            (self.mb['D'], f'https://open.spotify.com/track/{ID_D}'),
            (self.mb['F'], f'https://open.spotify.com/track/{ID_F}'),
            (self.mb['H'], f'https://open.spotify.com/track/{ID_SHARED}'),
            (self.mb['I'], f'https://open.spotify.com/track/{ID_SHARED}'),
            (self.mb['J'], f'https://open.spotify.com/track/{ID_J_MB}'),
            (self.mb['K'], f'https://open.spotify.com/track/{ID_K}'),
            (self.mb['L'], f'https://open.spotify.com/track/{ID_L_MB}'),
        ]
        MusicBrainzRecordingURL.objects.bulk_create([
            self._url(m, u, 'spotify') for m, u in urls
        ] + [
            self._url(self.mb['A'], 'https://music.apple.com/x', 'apple_music'),
            self._url(self.mb['A'], f'https://open.spotify.com/track/{ID_OTHER}', 'spotify', version='mb-old'),
        ])

        # Pending hydration: on A's item, on a one-hop redirect source into E, leased, already matched.
        self.phi_a = self._phi(self.items['A'], 'USA')
        self.redirect_source = self._item(mbid())
        CanonicalItemRedirect.objects.create(
            from_canonical_item=self.redirect_source, to_canonical_item=self.target_e,
            source='test', source_version='t', status='active',
        )
        self.phi_redirect = self._phi(self.redirect_source, 'USR')
        self.phi_leased = self._phi(
            self.items['A'], 'USLEASE', leased_by='worker', lease_expires_at=timezone.now() + timedelta(hours=1),
        )
        self.phi_matched = self._phi(self.items['A'], 'USM', status='matched')

    def _item(self, mbid_value):
        identity = identity_from_parts(item_type='recording_mbid', key_value=mbid_value)
        return CanonicalItem.objects.create(
            id=identity.item_id, item_type=identity.item_type, canonical_key=identity.canonical_key,
        )

    @staticmethod
    def _url(recording, url, provider, version=VERSION):
        return MusicBrainzRecordingURL(
            recording_mbid=recording, url=url, url_fingerprint=uuid.uuid4().hex, provider=provider,
            link_type_id=1, source_version=version,
        )

    def _phi(self, item, identifier, **kwargs):
        return ProviderHydrationItem.objects.create(
            canonical_item=item, provider='spotify', identifier_type='isrc', identifier=identifier, **kwargs,
        )

    def _precision_file(self, directory, **overrides):
        payload = {'source_version': VERSION, 'compared': 5000, 'precision': 0.99, **overrides}
        path = Path(directory) / 'precision.json'
        path.write_text(json.dumps(payload))
        return str(path)

    def _run(self, *args):
        out = io.StringIO()
        call_command(*args, stdout=out, stderr=io.StringIO())
        return out.getvalue()

    def test_latest_version_comes_from_the_bridge_run(self):
        self.assertEqual(latest_musicbrainz_url_source_version(), VERSION)

    def test_classification_covers_each_case(self):
        stats = build_workspace(VERSION)
        self.assertEqual(stats.url_rows, 12)  # the old-version and apple rows are not read
        self.assertEqual(stats.invalid_urls, 1)  # the artist link
        self.assertEqual(
            stats.status_counts,
            {
                'new': 2,            # A, D (-> E)
                'multiple_ids': 1,   # B
                'unresolved': 1,     # C
                'conflict_alias': 1,  # F
                'shared_id': 2,      # H, I
                'api_disagrees': 2,  # J, L
                'existing_same': 1,  # K
            },
        )

    def test_dry_run_writes_nothing(self):
        payload = json.loads(self._run('materialize_musicbrainz_url_aliases', '--json'))
        self.assertEqual(payload['mode'], 'dry-run')
        self.assertEqual(payload['aliases_would_create'], 2)
        self.assertEqual(payload['hydration_would_match'], 2)
        self.assertFalse(CanonicalItemAlias.objects.filter(metadata__match_source='musicbrainz_url').exists())
        self.assertEqual(ProviderHydrationItem.objects.filter(status='matched').count(), 1)
        self.assertEqual(CanonicalAliasMaterializationRun.objects.count(), 0)

    def test_write_requires_a_passing_precision_report(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(CommandError):
                self._run('materialize_musicbrainz_url_aliases', '--write')
            for overrides in (
                {'precision': 0.5},
                {'compared': 3},
                {'source_version': 'other'},
            ):
                with self.assertRaises(CommandError):
                    self._run(
                        'materialize_musicbrainz_url_aliases', '--write',
                        '--precision-report', self._precision_file(tmp, **overrides),
                    )
        self.assertFalse(CanonicalItemAlias.objects.filter(metadata__match_source='musicbrainz_url').exists())

    def test_write_creates_aliases_on_final_target_and_marks_hydration(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = json.loads(self._run(
                'materialize_musicbrainz_url_aliases', '--write', '--json',
                '--precision-report', self._precision_file(tmp),
            ))
        self.assertEqual(payload['aliases_created'], 2)
        alias_a = CanonicalItemAlias.objects.get(source='spotify', resource_type='track', source_id=ID_A)
        self.assertEqual(alias_a.canonical_item, self.items['A'])
        self.assertEqual(alias_a.metadata['match_source'], 'musicbrainz_url')
        self.assertEqual(alias_a.status, 'active')
        alias_d = CanonicalItemAlias.objects.get(source='spotify', resource_type='track', source_id=ID_D)
        self.assertEqual(alias_d.canonical_item, self.target_e)  # post-redirect target, not D's own item
        # Never overwritten / never created for ambiguous cases.
        self.assertEqual(
            CanonicalItemAlias.objects.get(source_id=ID_F).canonical_item, self.owner_other,
        )
        for spotify_id in (ID_B1, ID_B2, ID_SHARED, ID_J_MB, ID_L_MB, 'C' * 22, ID_OTHER):
            self.assertFalse(CanonicalItemAlias.objects.filter(source='spotify', source_id=spotify_id).exists())

        self.phi_a.refresh_from_db()
        self.phi_redirect.refresh_from_db()
        self.phi_leased.refresh_from_db()
        self.phi_matched.refresh_from_db()
        self.assertEqual(self.phi_a.status, 'matched')
        self.assertEqual(self.phi_a.evidence['matched_by'], 'musicbrainz_url')
        self.assertEqual(self.phi_redirect.status, 'matched')
        self.assertEqual(self.phi_leased.status, 'pending')  # leased rows are skipped
        self.assertEqual(self.phi_leased.leased_by, 'worker')
        self.assertEqual(self.phi_matched.status, 'matched')

    def test_rerun_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self._precision_file(tmp)
            self._run('materialize_musicbrainz_url_aliases', '--write', '--precision-report', report)
            before = CanonicalItemAlias.objects.count()
            payload = json.loads(self._run(
                'materialize_musicbrainz_url_aliases', '--write', '--json', '--precision-report', report,
            ))
        self.assertEqual(CanonicalItemAlias.objects.count(), before)
        self.assertEqual(payload['aliases_created'], 0)
        self.assertEqual(payload['hydration_matched'], 0)

    def test_batches_are_resumable(self):
        with tempfile.TemporaryDirectory() as tmp:
            report = self._precision_file(tmp)
            first = json.loads(self._run(
                'materialize_musicbrainz_url_aliases', '--write', '--json', '--batch-size', '1',
                '--max-batches', '1', '--precision-report', report,
            ))
            self.assertEqual(first['status'], 'paused')
            self.assertEqual(first['aliases_created'], 1)
            run = CanonicalAliasMaterializationRun.objects.get(pk=first['run_id'])
            self.assertEqual(run.status, 'pending')
            self.assertIn('last_mbid', run.checkpoints)
            second = json.loads(self._run(
                'materialize_musicbrainz_url_aliases', '--write', '--json', '--batch-size', '1',
                '--resume-run-id', first['run_id'], '--precision-report', report,
            ))
        self.assertEqual(second['status'], 'complete')
        self.assertEqual(second['aliases_created'], 2)
        self.assertEqual(CanonicalItemAlias.objects.filter(metadata__match_source='musicbrainz_url').count(), 2)
        self.phi_a.refresh_from_db()
        self.assertEqual(self.phi_a.status, 'matched')

    def test_precision_check_is_read_only_and_reports_three_outcomes(self):
        counts_before = (
            CanonicalItemAlias.objects.count(),
            ProviderHydrationItem.objects.filter(status='matched').count(),
        )
        with tempfile.TemporaryDirectory() as tmp:
            out_path = Path(tmp) / 'report.json'
            payload = json.loads(self._run('check_musicbrainz_url_precision', '--out', str(out_path)))
            self.assertEqual(json.loads(out_path.read_text())['same'], 1)
        self.assertEqual(payload['compared'], 3)
        self.assertEqual(payload['same'], 1)                 # K
        self.assertEqual(payload['different_same_isrc'], 1)  # L: Spotify returned both for the ISRC
        self.assertEqual(payload['different'], 1)            # J
        self.assertAlmostEqual(payload['precision'], 2 / 3)
        self.assertAlmostEqual(payload['strict_precision'], 1 / 3)
        self.assertEqual(payload['examples'][0]['api_spotify_id'] in (ID_J_API, ID_L_API), True)
        self.assertEqual(
            counts_before,
            (CanonicalItemAlias.objects.count(), ProviderHydrationItem.objects.filter(status='matched').count()),
        )

    def test_mbid_prefix_limits_the_slice(self):
        prefix = str(self.mb['A']).replace('-', '')[:8]
        stats = build_workspace(VERSION, mbid_prefix=prefix)
        self.assertEqual(stats.staged_pairs, 1)
        self.assertEqual(stats.status_counts, {'new': 1})

    def test_evidence_export_lists_multi_id_recordings(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'evidence.tsv'
            self._run('materialize_musicbrainz_url_aliases', '--evidence-path', str(path))
            lines = path.read_text().splitlines()
        self.assertEqual(lines[0], 'recording_mbid\tspotify_track_id')
        self.assertEqual(sorted(line.split('\t')[1] for line in lines[1:]), sorted([ID_B1, ID_B2]))

    def test_explain_flag_returns_plans_for_main_statements(self):
        stats = build_workspace(VERSION, explain=True)
        self.assertEqual(set(stats.explains), {'resolve_items', 'load_spotify_aliases', 'redirect_hop'})
        for lines in stats.explains.values():
            self.assertTrue(lines)
