import json
import uuid
from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from mlcore.models import (
    CanonicalItem,
    CanonicalItemAlias,
    ListenBrainzSessionTrack,
    ProviderHydrationItem,
    ProviderHydrationRun,
)
from mlcore.services.provider_hydration import (
    UNSCORED_PRIORITY,
    claim_hydration_item,
    listen_popularity,
    priority_for_popularity,
    rescore_pending_priorities,
    seed_spotify_hydration_queue_incrementally,
)


class PriorityMappingTests(SimpleTestCase):
    def test_more_popular_items_get_lower_priority_numbers_inside_1_to_99(self):
        scores = [0.5, 1, 3, 10, 100, 10_000, 10**9]
        priorities = [priority_for_popularity(score) for score in scores]
        self.assertEqual(priorities, sorted(priorities, reverse=True))
        self.assertTrue(all(1 <= priority <= 99 for priority in priorities))
        self.assertEqual(priority_for_popularity(0), UNSCORED_PRIORITY)
        self.assertLess(max(priorities), UNSCORED_PRIORITY)


class QueueFixtureMixin:
    def item(self, isrc, *, sessions=0, plays_per_session=1, status='pending', seeded=True):
        canonical = CanonicalItem.objects.create(
            id=uuid.uuid4(), item_type='recording_mbid', canonical_key=f'recording_mbid:{uuid.uuid4()}',
        )
        now = timezone.now()
        for _ in range(sessions):
            ListenBrainzSessionTrack.objects.create(
                session_key=uuid.uuid4().bytes * 2, canonical_item=canonical,
                first_played_at=now, last_played_at=now, play_count=plays_per_session,
            )
        CanonicalItemAlias.objects.create(
            canonical_item=canonical, source='isrc', resource_type='recording', source_id=isrc, status='active',
        )
        if seeded:
            return ProviderHydrationItem.objects.create(
                canonical_item=canonical, provider='spotify', identifier_type='isrc', identifier=isrc, status=status,
            )
        return canonical


class ListenPopularityTests(QueueFixtureMixin, TestCase):
    def test_distinct_sessions_outweigh_a_one_session_binge_and_unheard_items_are_absent(self):
        many = self.item('AAA000000001', sessions=20)
        binge = self.item('AAA000000002', sessions=1, plays_per_session=500)
        silent = self.item('AAA000000003')
        scores = listen_popularity([many.canonical_item_id, binge.canonical_item_id, silent.canonical_item_id])
        self.assertGreater(scores[many.canonical_item_id], scores[binge.canonical_item_id])
        self.assertEqual(scores[binge.canonical_item_id], 1.0, 'five hundred plays in one session count once')
        self.assertEqual(scores[many.canonical_item_id], 20.0)
        self.assertNotIn(silent.canonical_item_id, scores)
        self.assertEqual(listen_popularity([]), {})


class SeedAndClaimOrderTests(QueueFixtureMixin, TestCase):
    def test_seeding_scores_items_and_the_most_listened_are_claimed_first(self):
        for isrc, sessions in (('AAA000000001', 1), ('AAA000000002', 50), ('AAA000000003', 0), ('AAA000000004', 8)):
            self.item(isrc, sessions=sessions, seeded=False)

        result = seed_spotify_hydration_queue_incrementally(scan_limit=100)
        self.assertEqual(result.created, 4)

        run = ProviderHydrationRun.objects.create(provider='spotify')
        claimed = [claim_hydration_item(run=run, worker_id='w').identifier for _ in range(4)]
        self.assertEqual(claimed, ['AAA000000002', 'AAA000000004', 'AAA000000001', 'AAA000000003'])
        self.assertEqual(
            ProviderHydrationItem.objects.get(identifier='AAA000000003').priority, UNSCORED_PRIORITY,
        )


class RescoreTests(QueueFixtureMixin, TestCase):
    def test_rescore_walks_the_queue_in_bounded_batches_and_only_writes_changes(self):
        hot = self.item('AAA000000001', sessions=30)
        warm = self.item('AAA000000002', sessions=3)
        cold = self.item('AAA000000003', sessions=0)
        running = self.item('AAA000000004', sessions=30, status='running')
        done = self.item('AAA000000005', sessions=30, status='matched')

        first = rescore_pending_priorities(batch_size=2)
        self.assertEqual((first.scanned, first.updated, first.pass_complete), (2, 2, False))
        second = rescore_pending_priorities(after_id=first.next_cursor, batch_size=2)
        self.assertEqual((second.scanned, second.updated, second.pass_complete), (1, 0, True))
        self.assertEqual(second.next_cursor, 0)

        for item in (hot, warm, cold, running, done):
            item.refresh_from_db()
        self.assertLess(hot.priority, warm.priority)
        self.assertLess(warm.priority, UNSCORED_PRIORITY)
        self.assertEqual(cold.priority, UNSCORED_PRIORITY)
        self.assertEqual((running.priority, done.priority), (UNSCORED_PRIORITY, UNSCORED_PRIORITY))

        again = rescore_pending_priorities(batch_size=10)
        self.assertEqual(again.updated, 0, 'a second pass over unchanged data writes nothing')

    def test_new_listens_move_an_already_queued_item_up(self):
        late = self.item('AAA000000001', sessions=0)
        other = self.item('AAA000000002', sessions=2)
        rescore_pending_priorities(batch_size=10)
        late.refresh_from_db()
        self.assertEqual(late.priority, UNSCORED_PRIORITY)

        now = timezone.now()
        for _ in range(40):
            ListenBrainzSessionTrack.objects.create(
                session_key=uuid.uuid4().bytes * 2, canonical_item=late.canonical_item,
                first_played_at=now, last_played_at=now,
            )
        rescore_pending_priorities(batch_size=10)
        late.refresh_from_db()
        other.refresh_from_db()
        self.assertLess(late.priority, other.priority)

    def test_batch_size_must_be_positive(self):
        with self.assertRaises(ValueError):
            rescore_pending_priorities(batch_size=0)


class QueueCommandTests(QueueFixtureMixin, TestCase):
    def test_show_queue_prints_claim_order_with_scores(self):
        self.item('AAA000000001', sessions=1)
        self.item('AAA000000002', sessions=25)
        self.item('AAA000000003', sessions=0)
        rescore_pending_priorities(batch_size=10)
        output = StringIO()
        call_command('show_hydration_queue', limit=2, json=True, stdout=output)
        rows = json.loads(output.getvalue())
        self.assertEqual([row['identifier'] for row in rows], ['AAA000000002', 'AAA000000001'])
        self.assertGreater(rows[0]['listen_score'], rows[1]['listen_score'])
        self.assertLess(rows[0]['priority'], rows[1]['priority'])

        text = StringIO()
        call_command('show_hydration_queue', limit=5, stdout=text)
        self.assertIn('AAA000000002', text.getvalue().splitlines()[0])


class BackfillCommandTests(QueueFixtureMixin, TestCase):
    def test_backfill_command_runs_a_full_pass_in_batches(self):
        for number in range(5):
            self.item(f'AAA00000000{number}', sessions=number)
        output = StringIO()
        call_command('rescore_hydration_priority', batch_size=2, sleep_seconds=0, stdout=output)
        self.assertIn('pass_complete=True', output.getvalue().splitlines()[-1])
        self.assertEqual(len(output.getvalue().splitlines()), 3)
        priorities = list(ProviderHydrationItem.objects.order_by('identifier').values_list('priority', flat=True))
        self.assertEqual(priorities[0], UNSCORED_PRIORITY)
        self.assertEqual(priorities, sorted(priorities, reverse=True))

    def test_max_batches_stops_early_and_prints_the_cursor_to_resume(self):
        for number in range(5):
            self.item(f'AAA00000000{number}', sessions=1)
        output = StringIO()
        call_command('rescore_hydration_priority', batch_size=2, max_batches=1, sleep_seconds=0, stdout=output)
        self.assertIn('pass_complete=False', output.getvalue())
        self.assertEqual(ProviderHydrationItem.objects.filter(priority__lt=UNSCORED_PRIORITY).count(), 2)
