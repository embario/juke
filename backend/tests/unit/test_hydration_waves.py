import datetime
import uuid
from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase

from catalog.models import Album, Artist, Track
from mlcore.management.commands import hydrate_spotify_from_isrc as command
from mlcore.models import CanonicalItem, ItemCoOccurrence, ProviderHydrationItem, ProviderHydrationRun
from mlcore.services.hydration_waves import (
    WAVE_STEP,
    cooccurring_items,
    expand_wave,
    sibling_items,
    wave_priority,
)
from mlcore.services.provider_hydration import (
    UNSCORED_PRIORITY,
    ReconciliationResult,
    claim_hydration_item,
    rescore_pending_priorities,
)


class WavePriorityTests(SimpleTestCase):
    def test_each_hop_is_one_step_worse_and_stays_inside_1_to_99(self):
        self.assertEqual(wave_priority(20), 20 + WAVE_STEP)
        self.assertEqual(wave_priority(-25), 1, 'a user-boosted seed never pushes neighbours ahead of boosts')
        self.assertEqual(wave_priority(98), 99)


class QueueMixin:
    def canonical(self, track=None):
        return CanonicalItem.objects.create(
            id=uuid.uuid4(), item_type='recording_mbid', canonical_key=f'recording_mbid:{uuid.uuid4()}', track=track,
        )

    def queued(self, canonical=None, *, priority=UNSCORED_PRIORITY, status='pending'):
        canonical = canonical or self.canonical()
        return ProviderHydrationItem.objects.create(
            canonical_item=canonical, provider='spotify', identifier_type='isrc',
            identifier=f'ISRC{uuid.uuid4().hex[:8]}'.upper(), priority=priority, status=status,
        )

    def pair(self, one, two, *, co_count=5, pmi=1.0):
        a, b = sorted([one.id, two.id], key=str)
        ItemCoOccurrence.objects.create(item_a_juke_id=a, item_b_juke_id=b, co_count=co_count, pmi_score=pmi)

    def track(self, name, album, number):
        return Track.objects.create(
            name=name, spotify_id=f'sp-{uuid.uuid4().hex[:10]}', album=album, track_number=number, duration_ms=1000,
        )

    def album(self, name, artist):
        album = Album.objects.create(
            name=name, spotify_id=f'al-{uuid.uuid4().hex[:10]}', total_tracks=3, release_date=datetime.date(2020, 1, 1),
        )
        album.artists.add(artist)
        return album


class CooccurrenceTests(QueueMixin, TestCase):
    def test_neighbours_come_from_both_orientations_ranked_by_pmi_and_filtered_by_count(self):
        seed = self.canonical()
        near, mid, far, rare = (self.canonical() for _ in range(4))
        self.pair(seed, near, pmi=9.0)
        self.pair(seed, mid, pmi=5.0)
        self.pair(seed, far, pmi=1.0)
        self.pair(seed, rare, pmi=20.0, co_count=1)

        self.assertEqual(cooccurring_items(seed.id, 10), [near.id, mid.id, far.id])
        self.assertEqual(cooccurring_items(seed.id, 2), [near.id, mid.id])


class WaveTests(QueueMixin, TestCase):
    def test_a_hydrated_popular_item_raises_its_neighbours_capped_per_seed(self):
        seed = self.canonical()
        neighbours = [self.queued(priority=UNSCORED_PRIORITY) for _ in range(30)]
        for number, item in enumerate(neighbours):
            self.pair(seed, item.canonical_item, pmi=100.0 - number)
        bystander = self.queued()

        result = expand_wave([(seed.id, 20)], fan_out=10, sibling_fan_out=0)

        self.assertEqual((result.seeds_used, result.neighbors, result.rows_updated), (1, 10, 10))
        raised = ProviderHydrationItem.objects.filter(priority=wave_priority(20))
        self.assertEqual({item.pk for item in raised}, {item.pk for item in neighbours[:10]})
        bystander.refresh_from_db()
        self.assertEqual(bystander.priority, UNSCORED_PRIORITY)

    def test_total_updates_per_wave_are_capped_and_the_best_seeds_win(self):
        hub, minor = self.canonical(), self.canonical()
        hub_neighbours = [self.queued() for _ in range(6)]
        minor_neighbours = [self.queued() for _ in range(6)]
        for item in hub_neighbours:
            self.pair(hub, item.canonical_item)
        for item in minor_neighbours:
            self.pair(minor, item.canonical_item)

        result = expand_wave([(minor.id, 60), (hub.id, 10)], fan_out=6, max_updates=8)

        self.assertEqual(result.rows_updated, 8)
        self.assertEqual(ProviderHydrationItem.objects.filter(priority=wave_priority(10)).count(), 6)
        self.assertEqual(ProviderHydrationItem.objects.filter(priority=wave_priority(60)).count(), 2)

    def test_unpopular_seeds_do_not_expand_and_extra_seeds_wait_for_the_next_wave(self):
        seeds = [self.canonical() for _ in range(3)]
        for seed in seeds:
            self.pair(seed, self.queued().canonical_item)
        unpopular = self.canonical()
        self.pair(unpopular, self.queued().canonical_item)

        result = expand_wave(
            [(seeds[0].id, 30), (seeds[1].id, 20), (seeds[2].id, 40), (unpopular.id, 95)], max_seeds=2,
        )

        self.assertEqual(result.seeds_used, 2)
        self.assertEqual(result.remaining_seeds, [(seeds[2].id, 40)])
        self.assertEqual(ProviderHydrationItem.objects.filter(priority__lt=UNSCORED_PRIORITY).count(), 2)

    def test_a_slow_wave_stops_starting_new_seeds_and_hands_them_back(self):
        seeds = [self.canonical() for _ in range(4)]
        for seed in seeds:
            self.pair(seed, self.queued().canonical_item)
        clock = iter([0.0, 5.0, 25.0, 25.0, 25.0, 25.0])

        result = expand_wave(
            [(seed.id, 10 + number) for number, seed in enumerate(seeds)],
            time_budget_seconds=20, monotonic=lambda: next(clock),
        )

        self.assertEqual(result.seeds_used, 2)
        self.assertEqual([seed for seed, _priority in result.remaining_seeds], [seeds[2].id, seeds[3].id])
        self.assertEqual(ProviderHydrationItem.objects.filter(priority__lt=UNSCORED_PRIORITY).count(), 2)

    def test_waves_only_move_items_earlier_and_never_ahead_of_user_boosts(self):
        seed = self.canonical()
        boosted = self.queued(priority=-15)
        already_better = self.queued(priority=5)
        running = self.queued(status='running')
        plain = self.queued()
        for item in (boosted, already_better, running, plain):
            self.pair(seed, item.canonical_item)

        expand_wave([(seed.id, -20)])  # a user-boosted seed: neighbours land at priority 1

        for item in (boosted, already_better, running, plain):
            item.refresh_from_db()
        self.assertEqual((boosted.priority, already_better.priority), (-15, 1))
        self.assertEqual((running.priority, plain.priority), (UNSCORED_PRIORITY, 1))

    def test_siblings_on_the_album_and_by_the_artist_are_raised_with_their_own_cap(self):
        artist = Artist.objects.create(name='A', spotify_id='artist-a')
        album, other_album = self.album('One', artist), self.album('Two', artist)
        seed_track = self.track('seed', album, 1)
        same_album = self.track('same album', album, 2)
        same_artist = self.track('same artist', other_album, 1)
        stranger = self.track('stranger', self.album('Three', Artist.objects.create(name='B', spotify_id='artist-b')), 1)
        seed = self.canonical(seed_track)
        mates = {
            name: self.queued(self.canonical(track))
            for name, track in (('album', same_album), ('artist', same_artist), ('stranger', stranger))
        }

        self.assertEqual(
            set(sibling_items(seed.id, 5)), {mates['album'].canonical_item_id, mates['artist'].canonical_item_id},
        )
        self.assertEqual(sibling_items(seed.id, 1), [mates['album'].canonical_item_id])

        expand_wave([(seed.id, 10)], fan_out=0, sibling_fan_out=5)
        for item in mates.values():
            item.refresh_from_db()
        self.assertEqual((mates['album'].priority, mates['artist'].priority), (18, 18))
        self.assertEqual(mates['stranger'].priority, UNSCORED_PRIORITY)

    def test_claim_order_reflects_the_wave_and_a_rescore_does_not_undo_it(self):
        seed = self.canonical()
        plain = self.queued()
        neighbour = self.queued()
        self.pair(seed, neighbour.canonical_item)
        expand_wave([(seed.id, 30)])

        rescore_pending_priorities(batch_size=10)
        neighbour.refresh_from_db()
        self.assertEqual(neighbour.priority, wave_priority(30))

        run = ProviderHydrationRun.objects.create(provider='spotify')
        self.assertEqual(claim_hydration_item(run=run, worker_id='w').pk, neighbour.pk)
        self.assertEqual(claim_hydration_item(run=run, worker_id='w').pk, plain.pk)


class TailSweepTests(QueueMixin, TestCase):
    def test_a_tail_sweep_claim_takes_the_oldest_unscored_item_and_normal_claims_stay_popularity_first(self):
        popular = self.queued(priority=5)
        tail_old = self.queued()
        self.queued()
        run = ProviderHydrationRun.objects.create(provider='spotify')

        self.assertEqual(claim_hydration_item(run=run, worker_id='w', tail_sweep=True).pk, tail_old.pk)
        self.assertEqual(claim_hydration_item(run=run, worker_id='w').pk, popular.pk)

    def test_a_tail_sweep_with_no_unscored_items_falls_back_to_the_best_item(self):
        best = self.queued(priority=3)
        self.queued(priority=40)
        run = ProviderHydrationRun.objects.create(provider='spotify')
        self.assertEqual(claim_hydration_item(run=run, worker_id='w', tail_sweep=True).pk, best.pk)


class WorkerWaveTests(TestCase):
    def run_worker(self, claims, **options):
        base = 'mlcore.management.commands.hydrate_spotify_from_isrc.'
        with mock.patch(base + 'wait_for_database'), \
                mock.patch(base + 'spotify_worker_lock') as lock, \
                mock.patch(base + 'reconcile_stale_hydration_state', return_value=ReconciliationResult(0, 0)), \
                mock.patch(base + 'SpotifyClient'), \
                mock.patch(base + 'claim_hydration_item', side_effect=claims) as claim, \
                mock.patch(base + 'hydrate_spotify_item', return_value='matched'), \
                mock.patch(base + 'expand_wave', wraps=command.expand_wave) as wave, \
                mock.patch('time.sleep'):
            lock.return_value.__enter__.return_value = True
            call_command(
                'hydrate_spotify_from_isrc', skip_seed=True, skip_incremental_seed=True, skip_priority_rescore=True,
                exit_when_empty=True, rps=1, json=True, stdout=StringIO(), metrics_path='', **options,
            )
        return claim, wave, ProviderHydrationRun.objects.get()

    def items(self, count, priority):
        return [SimpleNamespace(canonical_item_id=uuid.uuid4(), priority=priority) for _ in range(count)]

    def test_matched_popular_items_trigger_waves_and_every_nth_claim_sweeps_the_tail(self):
        claim, wave, run = self.run_worker(
            self.items(4, 10) + [None], wave_interval_seconds=0.001, tail_sweep_every=2,
        )

        self.assertEqual([call.kwargs['tail_sweep'] for call in claim.call_args_list], [False, True, False, True, False])
        self.assertTrue(wave.called)
        self.assertGreaterEqual(run.metadata['wave_count'], 1)
        self.assertGreaterEqual(run.metadata['wave_seeds_total'], 1)

    def test_unpopular_matches_and_skip_wave_never_start_a_wave(self):
        _claim, wave, run = self.run_worker(self.items(3, 99) + [None], wave_interval_seconds=0.001)
        self.assertFalse(wave.called)
        self.assertNotIn('wave_count', run.metadata)
        ProviderHydrationRun.objects.all().delete()
        _claim, wave, _run = self.run_worker(self.items(3, 10) + [None], skip_wave=True, wave_interval_seconds=0.001)
        self.assertFalse(wave.called)
