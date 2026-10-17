import io
import json
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path

from django.core.management import call_command
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from mlcore.models import CanonicalItem, CanonicalItemAlias, CanonicalItemRedirect, ListenBrainzSessionTrack
from mlcore.services import identity_coverage
from mlcore.services.identity_coverage import (
    FINAL_TABLE,
    FLAGS_TABLE,
    PLAYS_TABLE,
    compute_play_weighted_coverage,
    render_coverage_metrics,
    sum_plays_sql,
    write_coverage_metrics,
)
from mlcore.services.redirect_writes import MAX_REDIRECT_DEPTH, explain


def make_item(item_type='recording_msid'):
    return CanonicalItem.objects.create(
        id=uuid.uuid4(), item_type=item_type, canonical_key=f'{item_type}:{uuid.uuid4()}',
    )


def redirect(source, target):
    CanonicalItemRedirect.objects.create(
        from_canonical_item=source, to_canonical_item=target, source='test', source_version='v1', status='active',
    )


def alias(item, source, resource_type, source_id, status='active'):
    CanonicalItemAlias.objects.create(
        canonical_item=item, source=source, resource_type=resource_type, source_id=source_id, status=status,
    )


def play(item, count):
    now = timezone.now()
    ListenBrainzSessionTrack.objects.create(
        session_key=uuid.uuid4().bytes * 2, canonical_item=item, first_played_at=now, last_played_at=now, play_count=count,
    )


class IdentityCoverageTests(TestCase):
    def setUp(self):
        self.mbid_m = make_item('recording_mbid')
        alias(self.mbid_m, 'isrc', 'recording', 'USAAA0000001')
        self.msid_a = make_item()
        redirect(self.msid_a, self.mbid_m)
        self.msid_e = make_item()
        redirect(self.msid_e, self.msid_a)  # two-hop legacy chain e -> a -> m
        self.msid_b = make_item()
        alias(self.msid_b, 'spotify', 'track', '4uLU6hMCjMI75M1A2tKUQC')
        self.mbid_c = make_item('recording_mbid')
        self.msid_d = make_item()
        alias(self.msid_d, 'spotify', 'track', '1DFixLWgh2zZWvxKbdw5Rk', status='retired')  # inactive: not coverage
        self.cycle_f, self.cycle_g = make_item(), make_item()
        redirect(self.cycle_f, self.cycle_g)
        redirect(self.cycle_g, self.cycle_f)
        for item, count in (
            (self.msid_a, 4), (self.msid_a, 6), (self.msid_e, 1), (self.msid_b, 5), (self.mbid_c, 3),
            (self.msid_d, 2), (self.cycle_f, 7),
        ):
            play(item, count)

    def test_play_weighted_coverage_follows_redirects_and_counts_final_targets(self):
        coverage = compute_play_weighted_coverage()

        # All 28 plays stay in the denominator; the cycle's 7 plays remain uncovered.
        self.assertEqual(coverage.total_plays, 28)
        self.assertEqual(coverage.unresolved_plays, 7)
        self.assertEqual(coverage.total_items, 4)  # m, b, c, d (a and e share m)
        self.assertEqual(coverage.covered_plays, {'mbid': 14, 'isrc': 11, 'spotify': 5})
        self.assertEqual(coverage.covered_items, {'mbid': 2, 'isrc': 1, 'spotify': 1})
        self.assertAlmostEqual(coverage.play_ratio('mbid'), 14 / 28)
        self.assertAlmostEqual(coverage.item_ratio('spotify'), 1 / 4)

    def test_staging_tables_are_dropped(self):
        compute_play_weighted_coverage()
        with connection.cursor() as cursor:
            for table in (PLAYS_TABLE, FINAL_TABLE, FLAGS_TABLE):
                cursor.execute('SELECT to_regclass(%s)', [table])
                self.assertIsNone(cursor.fetchone()[0], table)

    def test_empty_corpus_is_all_zero_not_an_error(self):
        ListenBrainzSessionTrack.objects.all().delete()
        coverage = compute_play_weighted_coverage()
        self.assertEqual((coverage.total_plays, coverage.play_ratio('mbid'), coverage.item_ratio('isrc')), (0, 0.0, 0.0))

    def test_sampling_scans_a_tablesample_and_validates_input(self):
        self.assertIn('TABLESAMPLE SYSTEM (25.0)', sum_plays_sql(25))
        self.assertNotIn('TABLESAMPLE', sum_plays_sql(100))
        coverage = compute_play_weighted_coverage(sample_percent=50)
        for scheme in ('mbid', 'isrc', 'spotify'):
            self.assertTrue(0.0 <= coverage.play_ratio(scheme) <= 1.0)
        for kwargs in ({'sample_percent': 0}, {'sample_percent': 101}, {'staging_tablespace': 'x; DROP TABLE y'}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    compute_play_weighted_coverage(**kwargs)

    def test_metrics_file_is_prometheus_text_and_written_atomically(self):
        coverage = compute_play_weighted_coverage()
        text = render_coverage_metrics(coverage, now=datetime(2026, 10, 17, tzinfo=UTC))
        self.assertIn('mlcore_identity_play_coverage_ratio{scheme="mbid",sample_percent="100"} 0.50000000', text)
        self.assertIn('mlcore_identity_play_coverage_ratio{scheme="spotify",sample_percent="100"} 0.17857143', text)
        self.assertIn('mlcore_identity_coverage_plays{scheme="all",sample_percent="100"} 28', text)
        self.assertIn('mlcore_identity_coverage_plays{scheme="unresolved_redirect_depth",sample_percent="100"} 7', text)
        self.assertIn('mlcore_identity_coverage_last_success_timestamp_seconds 1792195200', text)
        with tempfile.TemporaryDirectory() as directory:
            path = write_coverage_metrics(coverage, Path(directory) / 'nested' / 'mlcore_identity_coverage.prom')
            self.assertTrue(path.read_text().startswith('# HELP'))
            self.assertFalse(list(Path(directory).rglob('*.tmp')))

    def test_command_writes_the_textfile(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'coverage.prom'
            stdout, stderr = io.StringIO(), io.StringIO()
            call_command('export_identity_coverage_metrics', '--metrics-path', str(target), '--json', stdout=stdout, stderr=stderr)
            payload = json.loads(stdout.getvalue())
            self.assertEqual(payload['total_plays'], 28)
            self.assertEqual(payload['play_coverage']['mbid'], round(14 / 28, 6))
            self.assertIn('mlcore_identity_play_coverage_ratio', target.read_text())
            self.assertIn('event=coverage', stderr.getvalue())

    def test_plans_are_set_based(self):
        """Prints EXPLAIN for the PR description."""
        with connection.cursor() as cursor:
            cursor.execute(
                f'CREATE TEMP TABLE {PLAYS_TABLE} (item_id uuid PRIMARY KEY, final_id uuid NOT NULL, '
                'depth integer NOT NULL, plays bigint NOT NULL)'
            )
            cursor.execute(
                f'CREATE TEMP TABLE {FINAL_TABLE} (final_id uuid PRIMARY KEY, plays bigint NOT NULL, '
                'resolved boolean NOT NULL, is_mbid boolean NOT NULL DEFAULT FALSE, has_isrc boolean NOT NULL DEFAULT FALSE, '
                'has_spotify boolean NOT NULL DEFAULT FALSE)'
            )
            cursor.execute(
                f'CREATE TEMP TABLE {FLAGS_TABLE} (final_id uuid PRIMARY KEY, has_isrc boolean NOT NULL, has_spotify boolean NOT NULL)'
            )
        plans = {
            'sum plays per item (full scan)': explain(sum_plays_sql(100), bulk=False),
            'follow one redirect hop': explain(
                'UPDATE ' + PLAYS_TABLE + ' t SET final_id = redirect.to_canonical_item_id, depth = t.depth + 1 '
                "FROM mlcore_canonical_item_redirect redirect WHERE redirect.from_canonical_item_id = t.final_id "
                "AND redirect.status = 'active' AND t.depth < %s", [MAX_REDIRECT_DEPTH]),
            'group by final target': explain(identity_coverage.GROUP_FINAL_SQL, [MAX_REDIRECT_DEPTH]),
            'flag MBID items': explain(identity_coverage.MBID_SQL, ['recording_mbid']),
            'flag ISRC / Spotify aliases': explain(identity_coverage.FLAGS_SQL),
        }
        for name, plan in plans.items():
            print(f'\nEXPLAIN {name}\n' + '\n'.join(plan))
            self.assertNotIn('Nested Loop', '\n'.join(plan), name)
