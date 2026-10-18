import io
import json
import uuid
from datetime import timedelta

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from mlcore.models import CanonicalItem, CanonicalItemAlias, CanonicalItemRedirect, ProviderHydrationItem
from mlcore.services import hydration_reconcile
from mlcore.services.hydration_reconcile import (
    APPLY_SLICE_SQL,
    RESOLVE_SQL,
    STAGE_TABLE,
    reconcile_hydration_with_spotify_aliases,
)
from mlcore.services.provider_hydration import (
    seed_spotify_hydration_queue,
    seed_spotify_hydration_queue_incrementally,
)
from mlcore.services.redirect_writes import MAX_REDIRECT_DEPTH, explain

SPOTIFY_Y = '4uLU6hMCjMI75M1A2tKUQC'
SPOTIFY_P = '1DFixLWgh2zZWvxKbdw5Rk'


def make_item(item_type='recording_msid'):
    return CanonicalItem.objects.create(
        id=uuid.uuid4(), item_type=item_type, canonical_key=f'{item_type}:{uuid.uuid4()}',
    )


def redirect(source, target):
    CanonicalItemRedirect.objects.create(
        from_canonical_item=source, to_canonical_item=target, source='test', source_version='v1', status='active',
    )


def spotify_alias(item, spotify_id):
    CanonicalItemAlias.objects.create(
        canonical_item=item, source='spotify', resource_type='track', source_id=spotify_id, status='active',
    )


def isrc_alias(item, isrc):
    CanonicalItemAlias.objects.create(
        canonical_item=item, source='isrc', resource_type='recording', source_id=isrc, status='active',
    )


def queue(item, identifier, **fields):
    return ProviderHydrationItem.objects.create(
        canonical_item=item, provider='spotify', identifier_type='isrc', identifier=identifier, **fields,
    )


class HydrationReconcileTests(TestCase):
    def setUp(self):
        self.mbid_y = make_item('recording_mbid')
        spotify_alias(self.mbid_y, SPOTIFY_Y)
        self.msid_x = make_item()
        redirect(self.msid_x, self.mbid_y)
        self.msid_chain_z = make_item()
        redirect(self.msid_chain_z, self.msid_x)  # legacy two-hop chain z -> x -> y
        self.own_p = make_item('recording_mbid')
        spotify_alias(self.own_p, SPOTIFY_P)
        self.no_spotify_q = make_item()

        self.via_redirect = queue(self.msid_x, 'USAAA0000001')
        self.via_chain = queue(self.msid_chain_z, 'USAAA0000002')
        self.own_alias_retry = queue(self.own_p, 'USAAA0000003', status='retry')
        self.no_answer = queue(self.no_spotify_q, 'USAAA0000004')
        self.running = queue(self.msid_x, 'USAAA0000005', status='running', leased_by='worker-1',
                             lease_expires_at=timezone.now() + timedelta(minutes=2))
        self.leased_pending = queue(self.msid_x, 'USAAA0000006', lease_expires_at=timezone.now() + timedelta(minutes=2))
        self.expired_lease = queue(self.msid_x, 'USAAA0000007', lease_expires_at=timezone.now() - timedelta(minutes=2))
        self.already_matched = queue(self.msid_x, 'USAAA0000008', status='matched', evidence={'resolved_by': 'api'})
        self.no_match = queue(self.msid_x, 'USAAA0000009', status='no_match')

    def _status(self, item):
        item.refresh_from_db()
        return item.status

    def test_marks_items_whose_final_target_has_a_spotify_alias(self):
        result = reconcile_hydration_with_spotify_aliases()

        for matched, spotify in (
            (self.via_redirect, SPOTIFY_Y), (self.via_chain, SPOTIFY_Y), (self.own_alias_retry, SPOTIFY_P),
            (self.expired_lease, SPOTIFY_Y),
        ):
            matched.refresh_from_db()
            self.assertEqual(matched.status, 'matched', matched.identifier)
            self.assertEqual(matched.evidence['resolved_by'], 'final_target_spotify_alias')
            self.assertEqual(matched.evidence['spotify_id'], spotify)
            self.assertEqual(matched.evidence['reconciled_by'], 'reconcile_hydration_aliases')
            self.assertEqual((matched.leased_by, matched.lease_expires_at, matched.next_attempt_at), ('', None, None))
        self.assertEqual(
            self.via_redirect.evidence['final_canonical_item_id'], str(self.mbid_y.id),
        )
        self.assertEqual(self.via_chain.evidence['final_canonical_item_id'], str(self.mbid_y.id))
        self.assertEqual(self._status(self.no_answer), 'pending')
        self.assertEqual(result.matched, 4)
        self.assertEqual(result.resolvable, 4)
        self.assertEqual(result.staged, 5)  # not running, not leased, not terminal
        self.assertEqual(result.skipped_busy, 0)

    def test_running_leased_and_terminal_rows_are_never_touched(self):
        reconcile_hydration_with_spotify_aliases()

        self.running.refresh_from_db()
        self.assertEqual((self.running.status, self.running.leased_by), ('running', 'worker-1'))
        self.assertEqual(self._status(self.leased_pending), 'pending')
        self.assertIsNotNone(ProviderHydrationItem.objects.get(pk=self.leased_pending.pk).lease_expires_at)
        self.assertEqual(self._status(self.no_match), 'no_match')
        self.already_matched.refresh_from_db()
        self.assertEqual(self.already_matched.evidence, {'resolved_by': 'api'})

    def test_rerun_is_idempotent_and_batches_do_not_change_the_outcome(self):
        reconcile_hydration_with_spotify_aliases(batch_size=1)
        first = dict(ProviderHydrationItem.objects.values_list('id', 'status'))
        again = reconcile_hydration_with_spotify_aliases(batch_size=2)

        self.assertEqual(dict(ProviderHydrationItem.objects.values_list('id', 'status')), first)
        self.assertEqual((again.matched, again.resolvable), (0, 0))

    def test_dry_run_counts_without_writing(self):
        result = reconcile_hydration_with_spotify_aliases(dry_run=True)

        self.assertEqual((result.resolvable, result.matched, result.dry_run), (4, 0, True))
        self.assertEqual(self._status(self.via_redirect), 'pending')

    def test_after_id_and_limit_bound_the_scan(self):
        result = reconcile_hydration_with_spotify_aliases(after_id=self.via_chain.id)
        self.assertEqual(self._status(self.via_redirect), 'pending')
        self.assertEqual(self._status(self.via_chain), 'pending')
        self.assertEqual(self._status(self.own_alias_retry), 'matched')
        self.assertEqual(result.matched, 2)  # own_alias_retry and expired_lease

        limited = reconcile_hydration_with_spotify_aliases(limit=1)
        self.assertEqual(limited.staged, 1)
        self.assertEqual(limited.matched, 1)

    def test_a_redirect_cycle_is_reported_not_matched(self):
        f, g = make_item(), make_item()
        redirect(f, g)
        redirect(g, f)
        queue(f, 'USAAA0000010')

        result = reconcile_hydration_with_spotify_aliases(dry_run=True)

        self.assertEqual(result.unresolved_redirect_depth, 1)
        self.assertEqual(result.resolvable, 4)

    def test_progress_and_options(self):
        events = []
        reconcile_hydration_with_spotify_aliases(batch_size=2, progress_callback=events.append)
        names = [event['event'] for event in events]
        self.assertIn('reconcile_staged', names)
        self.assertIn('reconcile_batch', names)
        self.assertGreaterEqual(names.count('reconcile_batch'), 2)
        last = [event for event in events if event['event'] == 'reconcile_batch'][-1]
        self.assertEqual((last['processed'], last['resolvable']), (4, 4))
        for kwargs in ({'batch_size': 0}, {'limit': 0}, {'staging_tablespace': 'x; DROP TABLE y'}):
            with self.subTest(kwargs=kwargs):
                with self.assertRaises(ValueError):
                    reconcile_hydration_with_spotify_aliases(**kwargs)

    def test_staging_tables_are_dropped_afterwards(self):
        reconcile_hydration_with_spotify_aliases()
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute('SELECT to_regclass(%s)', [STAGE_TABLE])
            self.assertIsNone(cursor.fetchone()[0])

    def test_command_reports_json(self):
        stdout, stderr = io.StringIO(), io.StringIO()
        call_command('reconcile_hydration_aliases', '--batch-size', '2', '--json', stdout=stdout, stderr=stderr)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload['matched'], 4)
        self.assertIn('event=reconcile_batch', stderr.getvalue())

    def test_plans_are_set_based(self):
        """Prints EXPLAIN for the PR description."""
        from django.db import connection
        with connection.cursor() as cursor:
            cursor.execute(
                f'CREATE TEMP TABLE {STAGE_TABLE} (item_id bigint PRIMARY KEY, final_id uuid NOT NULL, '
                'depth integer NOT NULL, spotify_id varchar(512))'
            )
            cursor.execute(
                f'CREATE TEMP TABLE {hydration_reconcile.ALIAS_TABLE} '
                '(canonical_item_id uuid PRIMARY KEY, spotify_id varchar(512) NOT NULL)'
            )
        from mlcore.services.identity_safety import stage_holds
        stage_holds()
        plans = {
            'stage pending queue rows': explain(hydration_reconcile.STAGE_PENDING_SQL, ['spotify', 0], bulk=False),
            'stage Spotify aliases': explain(hydration_reconcile.STAGE_SPOTIFY_ALIASES_SQL, bulk=False),
            'resolve (staged x staged, hash join forced)': explain(RESOLVE_SQL, [MAX_REDIRECT_DEPTH]),
            'apply slice (primary-key range)': explain(APPLY_SLICE_SQL, ['x', 'y', 0, 50000, 0, 50000, 0, 50000], bulk=False),
        }
        for name, plan in plans.items():
            print(f'\nEXPLAIN {name}\n' + '\n'.join(plan))
        self.assertNotIn('Nested Loop', '\n'.join(plans['resolve (staged x staged, hash join forced)']))


class SeedingSkipsResolvedItemsTests(TestCase):
    def setUp(self):
        self.mbid_y = make_item('recording_mbid')
        spotify_alias(self.mbid_y, SPOTIFY_Y)
        self.msid_x = make_item()
        redirect(self.msid_x, self.mbid_y)
        isrc_alias(self.msid_x, 'USAAA0000001')  # offline answer through the redirect
        self.plain = make_item()
        isrc_alias(self.plain, 'USAAA0000002')  # genuinely needs the API
        self.own = make_item('recording_mbid')
        spotify_alias(self.own, SPOTIFY_P)
        isrc_alias(self.own, 'USAAA0000003')
        self.redirected_without_spotify = make_item()
        redirect(self.redirected_without_spotify, self.plain)
        isrc_alias(self.redirected_without_spotify, 'USAAA0000004')

    def test_full_seeding_skips_items_whose_final_target_has_spotify(self):
        created = seed_spotify_hydration_queue()

        identifiers = set(ProviderHydrationItem.objects.values_list('identifier', flat=True))
        self.assertEqual(identifiers, {'USAAA0000002', 'USAAA0000004'})
        self.assertEqual(created, 2)

    def test_incremental_seeding_skips_them_too(self):
        result = seed_spotify_hydration_queue_incrementally(scan_limit=10)

        self.assertEqual((result.scanned, result.created, result.pass_complete), (4, 2, True))
        self.assertFalse(ProviderHydrationItem.objects.filter(identifier='USAAA0000001').exists())

    def test_incremental_cursor_crosses_resolved_prefix_and_suffix(self):
        CanonicalItemAlias.objects.filter(source='isrc').delete()
        for number in range(1, 6):
            source = make_item()
            redirect(source, self.mbid_y)
            isrc_alias(source, f'USAAA{number:07d}')
        isrc_alias(self.plain, 'USAAA0000006')
        source = make_item()
        redirect(source, self.mbid_y)
        isrc_alias(source, 'USAAA0000007')

        cursor = ''
        for expected_cursor, expected_created in (
            ('USAAA0000002', 0), ('USAAA0000004', 0), ('USAAA0000006', 1),
        ):
            result = seed_spotify_hydration_queue_incrementally(after_source_id=cursor, scan_limit=2)
            self.assertEqual((result.scanned, result.created, result.pass_complete), (2, expected_created, False))
            self.assertEqual(result.next_cursor, expected_cursor)
            cursor = result.next_cursor
        result = seed_spotify_hydration_queue_incrementally(after_source_id=cursor, scan_limit=2)
        self.assertEqual((result.scanned, result.created, result.pass_complete, result.next_cursor), (1, 0, True, ''))
        self.assertEqual(list(ProviderHydrationItem.objects.values_list('identifier', flat=True)), ['USAAA0000006'])

    def test_seeding_query_plan(self):
        """Prints EXPLAIN for the PR description."""
        from mlcore.services.provider_hydration import _isrc_aliases_needing_spotify
        from django.db import connection
        raw = CanonicalItemAlias.objects.filter(
            source='isrc', resource_type='recording', status='active',
        ).order_by('source_id').values_list('pk', 'source_id')[:2]
        scanned = list(raw)
        bounded = (
            _isrc_aliases_needing_spotify().filter(pk__in=[pk for pk, _source_id in scanned])
            .values_list('canonical_item_id', 'source_id', 'source_version')
        )
        for name, queryset in (('raw seeding slice', raw), ('bounded seeding anti-join', bounded)):
            sql, params = queryset.query.sql_with_params()
            with connection.cursor() as cursor:
                cursor.execute('EXPLAIN ' + sql, params)
                plan = '\n'.join(row[0] for row in cursor.fetchall())
            print(f'\nEXPLAIN {name} (small fixture)\n{plan}')
            if name == 'raw seeding slice':
                self.assertIn('Limit', plan)
                self.assertNotIn('SubPlan', plan)
        self.assertEqual(list(bounded.values_list('source_id', flat=True)), ['USAAA0000002'])
